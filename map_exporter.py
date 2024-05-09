
import bpy
from bpy.props import (BoolProperty, FloatProperty, StringProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper, ExportHelper, orientation_helper, path_reference_mode, axis_conversion)
import bmesh
from mathutils import Matrix

import os
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

MAP_INDEX_FLAG = 0x00000001

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

class Node:
    def __init__(self, name, parent, transform):
        self.name = name
        self.parent = parent
        self.transform = transform

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

class Node:
    def __init__(self, name, parent_index, mesh_index, matrix):
        self.name = name
        self.mesh_index = mesh_index
        self.parent_index = parent_index
        self.matrix = matrix

class Texture:
    def __init__(self, name, filename):
        self.name = name
        self.filename = filename

class Scene:
    def __init__(self):
        self.mesh_array = []
        self.node_array = []
        self.texture_array = []
        self.min_vertex = [0, 0, 0]
        self.max_vertex = [0, 0, 0]

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
        self.data[pos : pos + 4] = struct.pack("=I", len(self.data) if (value == None) else value)

class Map_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.map"
    bl_label = "Export Map"

    index_meshes: BoolProperty(
        name="Index",
        description="Index all meshes.",
        default=False
    )

    triangulate_meshes: BoolProperty(
        name="Triangulate",
        description="Triangulate all meshes.",
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

        if self.index_meshes:
            flags |= MAP_INDEX_FLAG

        buffer.add(struct.pack("=I", MAP_SIGNATURE))
        buffer.add(struct.pack("=I", flags)) # info
        buffer.add(struct.pack("=I", 0), "mesh_array_count")
        buffer.add(struct.pack("=I", 0), "mesh_array_offset")
        buffer.add(struct.pack("=I", 0), "node_array_count")
        buffer.add(struct.pack("=I", 0), "node_array_offset")
        buffer.add(struct.pack("=I", 0), "texture_array_count")
        buffer.add(struct.pack("=I", 0), "texture_array_offset")

        buffer.patch("mesh_array_count", len(scene.mesh_array))
        buffer.patch("mesh_array_offset")
        for mesh in scene.mesh_array:
            buffer.add(struct.pack("=I", 0), "name_offset")
            buffer.add(struct.pack("=I", 0), "vertex_array_count")
            buffer.add(struct.pack("=I", 0), "vertex_array_offset")
            buffer.add(struct.pack("=I", 0), "polygon_array_count")
            buffer.add(struct.pack("=I", 0), "polygon_array_offset")

        for mesh in scene.mesh_array:
            buffer.patch("name_offset")
            print(mesh.name)
            buffer.add(struct.pack("={}sB".format(len(mesh.name)), mesh.name.encode("utf-8"), 0))

            if self.index_meshes:
                buffer.patch("vertex_array_count", len(mesh.vertex_set))
                buffer.patch("vertex_array_offset")
                for vertex in mesh.vertex_set:
                    position = vertex.position
                    if self.normalize_meshes:
                        position = (
                            position[0] / (scene.max_vertex[0] - scene.min_vertex[0]),
                            position[1] / (scene.max_vertex[1] - scene.min_vertex[1]),
                            position[2] / (scene.max_vertex[2] - scene.min_vertex[2])
                        )
                    buffer.add(struct.pack("=3f3f2f", *position, *vertex.normal, *vertex.uv))
                
                buffer.patch("polygon_array_count", len(mesh.polygon_array))
                buffer.patch("polygon_array_offset")
                for polygon in mesh.polygon_array:
                    buffer.add(struct.pack("=B{}I".format(len(polygon.indices)), len(polygon.indices), *polygon.indices))
                    if (len(polygon.indices) == 3):
                        buffer.add(struct.pack("=I", 0)) # if there are only 3 indices, pad to 4
            else:
                buffer.patch("vertex_array_count", len(mesh.polygon_array) * 3)
                buffer.patch("vertex_array_offset")

                for polygon in mesh.polygon_array:
                    if (len(polygon.indices) != 3):
                        raise Exception("Unindexed meshes can only have triangles")
                    for i in range(0, 3):
                        vertex = mesh.vertex_set[polygon.indices[i]]
                        buffer.add(struct.pack("=3f3f2f", *vertex.position, *vertex.normal, *vertex.uv))

        buffer.patch("node_array_count", len(scene.node_array))
        buffer.patch("node_array_offset")
        for node in scene.node_array:
            buffer.add(struct.pack("=I", 0), "name_offset")
            buffer.add(struct.pack("=I", 0), "matrix_offset")
            buffer.add(struct.pack("=I", 0), "parent_index")
            buffer.add(struct.pack("=I", 0), "mesh_index")

        for node in scene.node_array:
            buffer.patch("name_offset")
            buffer.add(struct.pack("={}sB".format(len(node.name)), node.name.encode("utf-8"), 0))
            buffer.patch("matrix_offset")
            buffer.add(struct.pack("=4f4f4f4f", *node.matrix[0], *node.matrix[1], *node.matrix[2], *node.matrix[3]))
            buffer.patch("parent_index")
            buffer.add(struct.pack("=i", node.parent_index))
            buffer.patch("mesh_index")
            buffer.add(struct.pack("=i", node.mesh_index))

        buffer.patch("texture_array_count", len(scene.texture_array))
        buffer.patch("texture_array_offset")
        for texture in scene.texture_array:
            buffer.add(struct.pack("=I", 0), "name_offset")
            buffer.add(struct.pack("=I", 0), "texture_filename_offset")
        
        for texture in scene.texture_array:
            buffer.patch("name_offset")
            buffer.add(struct.pack("={}sB".format(len(texture.name)), texture.name.encode("utf-8"), 0))
            buffer.patch("texture_filename_offset")
            buffer.add(struct.pack("={}sB".format(len(texture.filename)), texture.filename.encode("utf-8"), 0))

        f = open(self.filepath, "wb")
        f.write(buffer.data)
        f.close()

    def process(self):
        scene = Scene()

        mesh_map = {}
        node_map = {}

        for texture in bpy.data.images:
            scene.texture_array.append(Texture(texture.name, os.path.basename(texture.filepath)))

        for it in bpy.data.meshes:
            mesh = it.copy()

            if self.triangulate_meshes:
                bm = bmesh.new()
                bm.from_mesh(mesh)
                bmesh.ops.triangulate(bm, faces=bm.faces)
                bm.to_mesh(mesh)
                bm.free()

            uv_array = mesh.uv_layers.active.uv

            mesh_data = Mesh(it.name)
            for p in mesh.polygons:
                if p.loop_total != 3 and p.loop_total != 4:
                    raise Exception("mesh has unsupported polygons (count={})".format(p.loop_total))

                polygon = Polygon()
                for i in range(p.loop_start, p.loop_start + p.loop_total):
                    n = mesh.loops[i].normal
                    v = mesh.vertices[mesh.loops[i].vertex_index]
                    vertex = None

                    scene.min_vertex[0] = min(scene.min_vertex[0], v.co.x)
                    scene.min_vertex[1] = min(scene.min_vertex[1], v.co.y)
                    scene.min_vertex[2] = min(scene.min_vertex[2], v.co.z)

                    scene.max_vertex[0] = max(scene.max_vertex[0], v.co.x)
                    scene.max_vertex[1] = max(scene.max_vertex[1], v.co.y)
                    scene.max_vertex[2] = max(scene.max_vertex[2], v.co.z)

                    vertex = Vertex(v.co, n, uv_array[i].vector)
                    vertex.finalize()

                    index = mesh_data.vertex_map.get(vertex, -1)
                    if index == -1:
                        index = len(mesh_data.vertex_set)
                        mesh_data.vertex_map[vertex] = index
                        mesh_data.vertex_set.append(vertex)
                    polygon.indices.append(index)
                mesh_data.polygon_array.append(polygon)
            
            mesh_map[mesh.name] = len(scene.mesh_array)
            scene.mesh_array.append(mesh_data)
        
        for node in bpy.data.objects:
            parent = None if node.parent is None else node.parent.name
            node_map[node.name] = len(scene.node_array)
            scene.node_array.append(Node(node.name, node_map[node.parent.name] if (node.parent != None) else -1, mesh_map.get(node.data.name, -1), node.matrix_local.transposed()))

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
