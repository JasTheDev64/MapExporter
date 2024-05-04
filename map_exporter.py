
import bpy
from bpy.props import (BoolProperty, FloatProperty, StringProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper, ExportHelper, orientation_helper, path_reference_mode, axis_conversion)
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
    def __init__(self, name, parent, mesh_index, matrix):
        self.name = name
        self.mesh_index = mesh_index
        self.parent = parent
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

class Buffer:
    def __init__(self):
        self.data = bytearray()
        self.patch_list = {}
    
    def add(data, patch_name = None):
        if (patch_name) != None:
            self.patch_list.get(patch_name, []).append(len(self.data))
        self.data += data
    
    def patch(patch_name, value = None):
        if (patch_name not in self.patch_list):
            raise Exception("patch name {} not found".format(patch_name))
        pos = self.patch_list.get(patch_name).pop(0)
        self.data[pos : pos + 4] = struct.pack("=I", len(self.data) if (value == None) else value)

class Map_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.map"
    bl_label = "Export Map"

    filename_ext = ".map"

    def write_file(self, scene):
        buffer = Buffer()

        buffer.append(struct.pack("=I", MAP_SIGNATURE))
        buffer.append(struct.pack("=I", 0), "mesh_array_count")
        buffer.append(struct.pack("=I", 0), "mesh_array_offset")
        buffer.append(struct.pack("=I", 0), "node_array_count")
        buffer.append(struct.pack("=I", 0), "node_array_offset")
        buffer.append(struct.pack("=I", 0), "texture_array_count")
        buffer.append(struct.pack("=I", 0), "texture_array_offset")

        buffer.patch("mesh_array_count", len(scene.mesh_array))
        buffer.patch("mesh_array_offset")
        for mesh in scene.mesh_array:
            buffer.append(struct.pack("=I", 0), "name_offset")
            buffer.append(struct.pack("=I", 0), "vertex_array_count")
            buffer.append(struct.pack("=I", 0), "vertex_array_offset")
            buffer.append(struct.pack("=I", 0), "polygon_array_count")
            buffer.append(struct.pack("=I", 0), "polygon_array_offset")
        
        for mesh in scene.mesh_array:
            buffer.patch("name_offset")
            buffer.append(struct.pack("={}sB".format(len(mesh.name)), mesh.name.encode("utf-8"), 0))

            buffer.patch("vertex_array_count", len(mesh.vertex_set))
            buffer.patch("vertex_array_offset")
            for vertex in mesh.vertex_set:
                f.write(struct.pack("=3f3f2f", *vertex.position, *vertex.normal, *vertex.uv))
            
            buffer.patch("polygon_array_count", len(mesh.polygon_array))
            buffer.patch("polygon_array_offset")
            for polygon in mesh.polygon_array:
                f.write(struct.pack("=B{}I".format(len(polygon.indices)), polygon.indices))
                if (len(polygon.indices) == 3):
                    f.write(struct.pack("=I", 0)) # if there are only 3 indices, pad to 4

        buffer.patch("node_array_count", len(scene.node_array))
        buffer.patch("node_array_offset")
        for node in scene.node_array:
        
        f = open(self.filepath, "wb")
        f.write(buffer.data)
        f.close()

    def process(self):
        scene = Scene()

        mesh_map = {}
        node_map = {}

        for texture in bpy.data.images:
            scene.texture_array.append(Texture(texture.name, os.path.basename(texture.filepath)))

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
