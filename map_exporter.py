
import bpy
from bpy.props import (BoolProperty, FloatProperty, StringProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper, ExportHelper, orientation_helper, path_reference_mode, axis_conversion)
from mathutils import Matrix

import os

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
        self.index_count = 0
        self.index_array = []

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

class Map_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.map"
    bl_label = "Export Map"

    filename_ext = ".map"

    def write_file(self, scene):
        f = open(self.filepath, "wb")
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
                    polygon.index_count += 1
                    polygon.index_array.append(index)
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
