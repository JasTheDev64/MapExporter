#ifndef MAP_FORMAT_H
#define MAP_FORMAT_H

#include <stdint.h>

enum { map_signature = 0x0050414D };

struct map_header 
{
    uint32_t signature;
    uint32_t mesh_array_count;
    uint32_t mesh_array_offset;
    uint32_t node_array_count;
    uint32_t node_array_offset;
    uint32_t texture_array_count;
    uint32_t texture_array_offset;
};

struct map_mesh
{
    uint32_t name_offset;
    uint32_t vertex_array_count;
    uint32_t vertex_array_offset;
    uint32_t polygon_array_count;
    uint32_t polygon_array_offset;
};

struct map_node
{
    uint32_t name_offset;
    uint32_t matrix_offset;
    uint32_t parent_index;
    uint32_t mesh_index;
};

struct map_texture
{
    uint32_t name_offset;
    uint32_t texture_filename_offset;
};

struct map_vertex
{
    float position[3];
    float normal[3];
    float uv[2];
};

struct map_polygon
{
    uint8_t index_count;
    uint32_t index_array[4];
};

#endif // MAP_FORMAT_H
