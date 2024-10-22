
import bpy
from bpy.props import (BoolProperty, FloatProperty, StringProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper, ExportHelper, orientation_helper, path_reference_mode, axis_conversion)
import bmesh
from mathutils import Matrix

import struct

bl_info = {
    "name": "Map Exporter",
    "author": "Jas",
    "version": (0, 0, 1),
    "blender": (4, 1, 1),
    "location": "File > Import-Export",
    "description": "Map Exporter",
    "warning": "",
    "support": "COMMUNITY",
    "category": "Import-Export"
}

MAP_SIGNATURE = 0x0050414D # 'MAP\0'

MAP_FLAG__TRIANGULATED = 0x00000001
MAP_FLAG__NORMALIZED   = 0x00000002

NULL_MATRIX = [0] * 16

class Vertex:
    def __init__(self, p, n, uv):
        self.position = tuple(p)
        self.normal = tuple(n)
        self.uv = tuple(uv)
        self.hash_value = 0
    
    def finalize(self):
        self.hash_value = hash((self.position, self.normal, self.uv))

    def __eq__(self, other):
        return (self.position == other.position) and (self.normal == other.normal) and (self.uv == other.uv)

    def __hash__(self):
        return self.hash_value

class Polygon:
    def __init__(self):
        self.indices = []

class Bone:
    def __init__(self, name, offset_matrix):
        self.name = name
        self.offset_matrix = offset_matrix
    
class Mesh:
    def __init__(self, name):
        self.name = name
        self.vertex_set = []
        self.vertex_map = {}
        self.polygon_array = []
        self.min_vertex = [0, 0, 0]
        self.max_vertex = [0, 0, 0]

class Node:
    def __init__(self, name, parent_index, mesh_index, matrix):
        self.name = name
        self.mesh_index = mesh_index
        self.parent_index = parent_index
        self.matrix = (
            # Blender's Y and Z axis are swapped - pre-multiply by +90 rotation on X axis
            # to convert to the vulkan coordiante system
            (matrix[0][0], matrix[0][2], -matrix[0][1], matrix[0][3]),
            (matrix[1][0], matrix[1][2], -matrix[1][1], matrix[1][3]),
            (matrix[2][0], matrix[2][2], -matrix[2][1], matrix[2][3]),
            (matrix[3][0], matrix[3][2], -matrix[3][1], matrix[3][3])
        )

class Texture:
    def __init__(self, name, filename):
        self.name = name
        self.filename = filename

class Scene:
    def __init__(self):
        self.mesh_array = []
        self.node_array = []
        self.texture_array = []

class Buffer:
    def __init__(self):
        self.data = bytearray()
        self.patch_list = {}
    
    def add(self, data, patch_name = None):
        if (patch_name) != None:
            if (patch_name not in self.patch_list):
                self.patch_list[patch_name] = []
            self.patch_list[patch_name].append(len(self.data))
        self.data += data
    
    def patch(self, patch_name, value = None):
        if (patch_name not in self.patch_list):
            raise Exception("patch name {} not found".format(patch_name))
        pos = self.patch_list.get(patch_name).pop(0)
        if (value == None):
            self.data[pos : pos + 4] = struct.pack("=I", len(self.data))
        else:
            self.data[pos : pos + len(value)] = value

class Map_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.map"
    bl_label = "Export Map"

    assert_triangulation: BoolProperty(
        name="Assert Triangulation",
        description="Ensure all polygons are triangles.",
        default=False
    )
    
    normalize_meshes: BoolProperty(
        name="Normalize",
        description="Normalize the coordinates to the range [-1, +1]",
        default=False
    )

    filename_ext = ".map"

    def write_file(self, scene):
        buffer = Buffer()

        flags = 0

        if self.normalize_meshes:
            flags |= MAP_FLAG__NORMALIZED

        if self.assert_triangulation:
            flags |= MAP_FLAG__TRIANGULATED

        buffer.add(struct.pack("=I", MAP_SIGNATURE))
        buffer.add(struct.pack("=I", flags)) # info
        buffer.add(struct.pack("=I", 0), "mesh_array.length")
        buffer.add(struct.pack("=I", 0), "mesh_array.offset")
        buffer.add(struct.pack("=I", 0), "node_array.length")
        buffer.add(struct.pack("=I", 0), "node_array.offset")
        buffer.add(struct.pack("=I", 0), "texture_array.length")
        buffer.add(struct.pack("=I", 0), "texture_array.offset")

        buffer.patch("mesh_array.length", struct.pack("=I", len(scene.mesh_array)))
        buffer.patch("mesh_array.offset")
        for mesh in scene.mesh_array:
            buffer.add(struct.pack("=I", 0), "name.length")
            buffer.add(struct.pack("=I", 0), "name.offset")
            buffer.add(struct.pack("=I", 0), "vertex_array.length")
            buffer.add(struct.pack("=I", 0), "vertex_array.offset")
            buffer.add(struct.pack("=I", 0), "polygon_array.length")
            buffer.add(struct.pack("=I", 0), "polygon_array.offset")

        for mesh in scene.mesh_array:
            buffer.patch("name.length", struct.pack("=I", len(mesh.name)))
            buffer.patch("name.offset")
            buffer.add(struct.pack("={}sB".format(len(mesh.name)), mesh.name.encode("utf-8"), 0))

            buffer.patch("vertex_array.length", struct.pack("=I", len(mesh.vertex_set)))
            buffer.patch("vertex_array.offset")
            for vertex in mesh.vertex_set:
                position = vertex.position
                if self.normalize_meshes:
                    position = (
                        position[0] / (mesh.max_vertex[0] - mesh.min_vertex[0]),
                        position[1] / (mesh.max_vertex[1] - mesh.min_vertex[1]),
                        position[2] / (mesh.max_vertex[2] - mesh.min_vertex[2])
                    )
                buffer.add(struct.pack("=3f3f2f", *position, *vertex.normal, *vertex.uv))
            
            buffer.patch("polygon_array.length", struct.pack("=I", len(mesh.polygon_array)))
            buffer.patch("polygon_array.offset")
            for polygon in mesh.polygon_array:
                buffer.add(struct.pack("=B{}I".format(len(polygon.indices)), len(polygon.indices), *polygon.indices))
                if (len(polygon.indices) == 3):
                    buffer.add(struct.pack("=I", 0)) # if there are only 3 indices, pad to 4

        buffer.patch("node_array.length", struct.pack("=I", len(scene.node_array)))
        buffer.patch("node_array.offset")
        for node in scene.node_array:
            buffer.add(struct.pack("=I", 0), "name.length")
            buffer.add(struct.pack("=I", 0), "name.offset")
            buffer.add(struct.pack("=16f", *NULL_MATRIX), "matrix")
            buffer.add(struct.pack("=i", 0), "parent.index")
            buffer.add(struct.pack("=i", 0), "mesh.index")

        for node in scene.node_array:
            buffer.patch("name.length", struct.pack("=I", len(node.name)))
            buffer.patch("name.offset")
            buffer.add(struct.pack("={}sB".format(len(node.name)), node.name.encode("utf-8"), 0))
            buffer.patch("matrix", struct.pack("=4f4f4f4f", *node.matrix[0], *node.matrix[1], *node.matrix[2], *node.matrix[3]))
            buffer.patch("parent.index", struct.pack("=i", node.parent_index))
            buffer.patch("mesh.index", struct.pack("=i", node.mesh_index))

        buffer.patch("texture_array.length", struct.pack("=I", len(scene.texture_array)))
        buffer.patch("texture_array.offset")
        for texture in scene.texture_array:
            buffer.add(struct.pack("=I", 0), "name.length")
            buffer.add(struct.pack("=I", 0), "name.offset")
            buffer.add(struct.pack("=I", 0), "texture_filename.length")
            buffer.add(struct.pack("=I", 0), "texture_filename.offset")
        
        for texture in scene.texture_array:
            buffer.patch("name.length", struct.pack("=I", len(texture.name)))
            buffer.patch("name.offset")
            buffer.add(struct.pack("={}sB".format(len(texture.name)), texture.name.encode("utf-8"), 0))

            buffer.patch("texture_filename.length", struct.pack("=I", len(texture.filename)))
            buffer.patch("texture_filename.offset")
            buffer.add(struct.pack("={}sB".format(len(texture.filename)), texture.filename.encode("utf-8"), 0))

        f = open(self.filepath, "wb")
        f.write(buffer.data)
        f.close()

    def process(self):
        scene = Scene()

        mesh_map = {}
        node_map = {}

        for texture in bpy.data.images:
            if (texture.name != "Render Result"):
                scene.texture_array.append(Texture(texture.name, bpy.path.basename(texture.filepath)))

        for mesh in bpy.data.meshes:
            uv_array = mesh.uv_layers.active.uv

            mesh_data = Mesh(mesh.name)
            for p in mesh.polygons:
                if p.loop_total != 3 and p.loop_total != 4:
                    raise Exception("mesh has unsupported polygons (count={})".format(p.loop_total))

                polygon = Polygon()
                for i in range(p.loop_start, p.loop_start + p.loop_total):
                    n = mesh.loops[i].normal
                    v = mesh.vertices[mesh.loops[i].vertex_index]
                    vertex = None

                    mesh_data.min_vertex[0] = min(mesh_data.min_vertex[0], v.co.x)
                    mesh_data.min_vertex[1] = min(mesh_data.min_vertex[1], v.co.y)
                    mesh_data.min_vertex[2] = min(mesh_data.min_vertex[2], v.co.z)

                    mesh_data.max_vertex[0] = max(mesh_data.max_vertex[0], v.co.x)
                    mesh_data.max_vertex[1] = max(mesh_data.max_vertex[1], v.co.y)
                    mesh_data.max_vertex[2] = max(mesh_data.max_vertex[2], v.co.z)

                    vertex = Vertex(v.co, n, uv_array[i].vector)
                    vertex.finalize()

                    index = mesh_data.vertex_map.get(vertex, -1)
                    if index == -1:
                        index = len(mesh_data.vertex_set)
                        mesh_data.vertex_map[vertex] = index
                        mesh_data.vertex_set.append(vertex)
                    polygon.indices.append(index)
                if self.assert_triangulation and (len(polygon.indices) != 3):
                    raise Exception("Polygon in mesh {} not triangulated".format(mesh.name))
                mesh_data.polygon_array.append(polygon)
            
            mesh_map[mesh_data.name] = len(scene.mesh_array)
            scene.mesh_array.append(mesh_data)
        
        for node in bpy.data.objects:
            parent = node_map[node.parent.name] if (node.parent != None) else -1
            mesh = mesh_map.get(node.data.name, -1) if (node.data != None) else -1
            node_map[node.name] = len(scene.node_array)
            scene.node_array.append(Node(node.name, parent, mesh, node.matrix_local.transposed()))

        return scene

    def execute(self, context):
        try:
            scene = self.process()
            self.write_file(scene)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}

def menu_func_export(self, context):
    self.layout.operator(Map_Exporter.bl_idname, text="Map (.map)")

def register():
    bpy.utils.register_class(Map_Exporter)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(Map_Exporter)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
