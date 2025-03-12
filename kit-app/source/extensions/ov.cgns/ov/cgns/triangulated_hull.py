import numpy as np
import warp as wp
from pxr import Gf, UsdGeom, Vt


@wp.func
def sort2(a: wp.int32, b: wp.int32):
    if a < b:
        return a, b
    else:
        return b, a


@wp.func
def sort3(a: wp.int32, b: wp.int32, c: wp.int32):

    if a < b and a < c:
        x = a
        y, z = sort2(b, c)
    elif b < a and b < c:
        x = b
        y, z = sort2(a, c)
    elif c < a and c < b:
        x = c
        y, z = sort2(a, b)
    else:
        wp.printf("ERROR! Shouldn't be here!(%d,%d,%d)\n", a, b, c)
        x, y, z = a, b, c

    return wp.vec3i(x, y, z)

@wp.func
def sort3t(a: wp.int32, b: wp.int32, c: wp.int32):

    if a < b and a < c:
        x = a
        y, z = sort2(b, c)
    elif b < a and b < c:
        x = b
        y, z = sort2(a, c)
    elif c < a and c < b:
        x = c
        y, z = sort2(a, b)
    else:
        wp.printf("ERROR! Shouldn't be here!(%d,%d,%d)\n", a, b, c)
        x, y, z = a, b, c

    return x, y, z


@wp.func
def sort4(a: wp.int32, b: wp.int32, c: wp.int32, d: wp.int32):

    if a < b and a < c and a < d:
        x = a
        y, z, w = sort3t(b, c, d)
    elif b < a and b < c and b < d:
        x = b
        y, z, w = sort3t(a, c, d)
    elif c < a and c < b and c < d:
        x = c
        y, z, w = sort3t(a, b, d)
    elif d < a and d < b and d < c:
        x = d
        y, z, w = sort3t(a, b, c)
    else:
        wp.printf("ERROR! Shouldn't be here!(%d,%d,%d,%d)\n", a, b, c, d)
        x, y, z, w = a, b, c, d

    return wp.vec4i(x,y,z,w)


def sort2b(a: wp.int32, b: wp.int32):
    if a < b:
        return a, b
    else:
        return b, a


def sort3b(a: wp.int64, b: wp.int64, c: wp.int64):

    if a < b and a < c:
        x = a
        y, z = sort2b(b, c)
    elif b < a and b < c:
        x = b
        y, z = sort2b(a, c)
    elif c < a and c < b:
        x = c
        y, z = sort2b(a, b)
    else:
        print(f"ERROR! Shouldn't be here!({a},{b},{c}")
        x, y, z = a, b, c

    return (x, y, z)


import cupy as cp

@wp.func
def face_nodes_tet(face: wp.int32,
                   idx0: wp.int32,
                   idx1: wp.int32,
                   idx2: wp.int32,
                   idx3: wp.int32):

    if face == 0:
        return idx0,idx2,idx1
    elif face == 1:
        return idx0,idx1,idx3
    elif face == 2:
        return idx0,idx3,idx2
    elif face == 3:
        return idx1,idx2,idx3
    else:
        wp.printf("ERROR: 'face=%d' must be less < 4\n", face)
        return -1,-1,-1

#  HEX_8
#  https://cgns.github.io/CGNS_docs_current/sids/conv.html#unst_hexa
#  Note: CGNS has 1-based indexing, but assume that the index has been already corrected
#                    6                            5
#                    +----------------------------+
#                   /|                           /|
#                  / |                          / |
#                 /  |                         /  |
#                /   |                        /   |
#               /    |                     4 /    |
#            7 +-----+----------------------+     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     +----------------------+-----+ 1
#              |    / 2                     |    /
#              |   /                        |   /
#              |  /                         |  /
#              | /                          | /
#              |/                           |/
#              +----------------------------+
#              3                            0
#
# CGNS face ordering F0-F5: bottom, right, back, left, front, top
@wp.func
def face_nodes_hex(face: wp.int32,
                   v0: wp.int32,
                   v1: wp.int32,
                   v2: wp.int32,
                   v3: wp.int32,
                   v4: wp.int32,
                   v5: wp.int32,
                   v6: wp.int32,
                   v7: wp.int32):

    # bottom
    if face == 0:
        return v0, v3, v2, v1
    # right
    elif face == 1:
        return v0, v1, v5, v4
    # back
    elif face == 2:
        return v1, v2, v6, v5
    # left
    elif face == 3:
        return v2, v3, v7, v6
    # front
    elif face == 4:
        return v0, v4, v7, v3
    # top
    elif face == 5:
        return v4, v5, v6, v7
    else:
        wp.printf("ERROR: 'face=%d' must be less < 8\n", face)
        return v0,v1,v2,v3


# pure python version
def face_nodes_hex_(face,
                    v0,
                    v1,
                    v2,
                    v3,
                    v4,
                    v5,
                    v6,
                    v7):

    # bottom
    if face == 0:
        return [v0, v3, v2, v1]
    # right
    elif face == 1:
        return [v0, v1, v5, v4]
    # back
    elif face == 2:
        return [v1, v2, v6, v5]
    # left
    elif face == 3:
        return [v2, v3, v7, v6]
    # front
    elif face == 4:
        return [v0, v4, v7, v3]
    # top
    elif face == 5:
        return [v4, v5, v6, v7]
    else:
        print(f"ERROR: 'face={face}' must be less < 8")
        return [v0,v1,v2,v3]


@wp.func
def hash4(tuple4: wp.vec4i):
    a = tuple4.x
    b = tuple4.y
    c = tuple4.z
    d = tuple4.w
    # Constants chosen as prime numbers to help distribute the hash values uniformly
    prime1 = wp.int32(31)
    prime2 = wp.int32(37)
    prime3 = wp.int32(41)
    prime4 = wp.int32(43)

    # Initial hash value
    hash_value = wp.int32(0)

    # Mix each element of the tuple into the hash value
    hash_value = prime1 * hash_value + a
    hash_value = prime2 * hash_value + b
    hash_value = prime3 * hash_value + c
    hash_value = prime4 * hash_value + d

    # Ensure the hash value is only 32-bits AND positive (0x7F is 0111 1111)
    hash_value = hash_value & 0x7FFFFFFF

    # wp.printf("(%d,%d,%d,%d)->%d\n", a,b,c,d,hash_value)

    return wp.int32(hash_value)


@wp.func
def hash3(tuple3: wp.vec3i):
    a = tuple3.x
    b = tuple3.y
    c = tuple3.z

    # Constants chosen as prime numbers to help distribute the hash values uniformly
    prime1 = wp.int32(31)
    prime2 = wp.int32(37)
    prime3 = wp.int32(41)

    # Initial hash value
    hash_value = wp.int32(0)

    # Mix each element of the tuple into the hash value
    hash_value = prime1 * hash_value + a
    hash_value = prime2 * hash_value + b
    hash_value = prime3 * hash_value + c

    # Ensure the hash value is only 32-bits AND positive (0x7F is 0111 1111)
    hash_value = hash_value & 0x7FFFFFFF

    # wp.printf("(%d,%d,%d,%d)->%d\n", a,b,c,d,hash_value)

    return wp.int32(hash_value)



@wp.func
def insert_hash3(array_tuple: wp.array(dtype=wp.vec3i),
                array_offset: wp.array(dtype=wp.int32),
                array_count: wp.array(dtype=wp.int32),
                tuple3: wp.vec3i,
                map_size: wp.int32,
                count_mode: wp.bool):

    tuple3_sorted = sort3(tuple3.x, tuple3.y, tuple3.z)
    idx = hash3(tuple3_sorted) % map_size
    if idx >= array_offset.shape[0] or idx < 0:
        wp.printf("ERROR: Writing past hash offset memory (%d > %d)\n", idx, array_offset.shape[0])
        return -3

    if count_mode:
        wp.atomic_add(array_count, idx, 1)
        return 0
    else:
        map_idx = array_offset[idx]

    idx_offset = wp.atomic_add(array_count, idx, 1)
    empty_idx = map_idx + idx_offset

    if empty_idx >= array_tuple.shape[0] or empty_idx < 0:
        wp.printf("ERROR: Writing past hash memory (%d > %d)\n", empty_idx, array_tuple.shape[0])
        return -1
    array_tuple[empty_idx] = tuple3
    return 0


@wp.func
def insert_hash4(array_tuple: wp.array(dtype=wp.vec4i),
                array_offset: wp.array(dtype=wp.int32),
                array_count: wp.array(dtype=wp.int32),
                tuple4: wp.vec4i,
                map_size: wp.int32,
                count_mode: wp.bool):

    tuple4_sorted = sort4(tuple4.x, tuple4.y, tuple4.z, tuple4.w)
    idx = hash4(tuple4_sorted) % map_size
    if idx >= array_offset.shape[0] or idx < 0:
        wp.printf("ERROR: Writing past hash offset memory (%d > %d)\n", idx, array_offset.shape[0])
        return -3

    if count_mode:
        wp.atomic_add(array_count, idx, 1)
        return 0
    else:
        map_idx = array_offset[idx]

    idx_offset = wp.atomic_add(array_count, idx, 1)
    empty_idx = map_idx + idx_offset

    if empty_idx >= array_tuple.shape[0] or empty_idx < 0:
        wp.printf("ERROR: Writing past hash memory (%d > %d)\n", empty_idx, array_tuple.shape[0])
        return -1
    array_tuple[empty_idx] = tuple4
    return 0



#  HEX_8
#  https://cgns.github.io/CGNS_docs_current/sids/conv.html#unst_hexa
#  Note: CGNS has 1-based indexing, but assume that the index has been already corrected
#                    6                            5
#                    +----------------------------+
#                   /|                           /|
#                  / |                          / |
#                 /  |                         /  |
#                /   |                        /   |
#               /    |                     4 /    |
#            7 +-----+----------------------+     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     |                      |     |
#              |     +----------------------+-----+ 1
#              |    / 2                     |    /
#              |   /                        |   /
#              |  /                         |  /
#              | /                          | /
#              |/                           |/
#              +----------------------------+
#              3                            0
#
# CGNS face ordering F0-F5: bottom, right, back, left, front, top
@wp.func
def face_nodes_hex(face: wp.int32,
                   v0: wp.int32,
                   v1: wp.int32,
                   v2: wp.int32,
                   v3: wp.int32,
                   v4: wp.int32,
                   v5: wp.int32,
                   v6: wp.int32,
                   v7: wp.int32):

    # bottom
    if face == 0:
        return v0, v3, v2, v1
    # right
    elif face == 1:
        return v0, v1, v5, v4
    # back
    elif face == 2:
        return v1, v2, v6, v5
    # left
    elif face == 3:
        return v2, v3, v7, v6
    # front
    elif face == 4:
        return v0, v4, v7, v3
    # top
    elif face == 5:
        return v4, v5, v6, v7
    else:
        wp.printf("ERROR: 'face=%d' must be less < 8\n", face)
        return v0,v1,v2,v3


# pure python version
def face_nodes_hex_(face,
                    v0,
                    v1,
                    v2,
                    v3,
                    v4,
                    v5,
                    v6,
                    v7):

    # bottom
    if face == 0:
        return [v0, v3, v2, v1]
    # right
    elif face == 1:
        return [v0, v1, v5, v4]
    # back
    elif face == 2:
        return [v1, v2, v6, v5]
    # left
    elif face == 3:
        return [v2, v3, v7, v6]
    # front
    elif face == 4:
        return [v0, v4, v7, v3]
    # top
    elif face == 5:
        return [v4, v5, v6, v7]
    else:
        print(f"ERROR: 'face={face}' must be less < 8")
        return [v0,v1,v2,v3]



@wp.kernel
def build_edges_occurance_tet_warp_kernel(idx_elem: wp.array(dtype=wp.int32),
                                          array_tuple: wp.array(dtype=wp.vec3i),
                                          array_count: wp.array(dtype=wp.int32),
                                          array_offset: wp.array(dtype=wp.int32),
                                          map_size: wp.int32,
                                          count_mode: wp.bool,
                                          err_code: wp.array(dtype=wp.int32)
                                          ):

    tid = wp.tid()
    idx0 = idx_elem[4 * tid + 0]
    idx1 = idx_elem[4 * tid + 1]
    idx2 = idx_elem[4 * tid + 2]
    idx3 = idx_elem[4 * tid + 3]

    for i in range(4):
         fn0, fn1, fn2 = face_nodes_tet(i, idx0, idx1, idx2, idx3)
         # wp.printf("[%d]:%d = (%d,%d,%d,%d)\n", tid, i, fn0, fn1, fn2, fn3)
         tuple3 = wp.vec3i(fn0, fn1, fn2)
         ret = insert_hash3(array_tuple, array_offset, array_count, tuple3, map_size, count_mode)
         if ret != 0:
             err_code[0] = ret
             return

    err_code[0] = 0



@wp.kernel
def build_edges_occurance_hex_warp_kernel(idx_elem: wp.array(dtype=wp.int32),
                                          array_tuple: wp.array(dtype=wp.vec4i),
                                          array_count: wp.array(dtype=wp.int32),
                                          array_offset: wp.array(dtype=wp.int32),
                                          map_size: wp.int32,
                                          count_mode: wp.bool,
                                          err_code: wp.array(dtype=wp.int32)
                                          ):

    tid = wp.tid()
    idx0 = idx_elem[8 * tid + 0]
    idx1 = idx_elem[8 * tid + 1]
    idx2 = idx_elem[8 * tid + 2]
    idx3 = idx_elem[8 * tid + 3]
    idx4 = idx_elem[8 * tid + 4]
    idx5 = idx_elem[8 * tid + 5]
    idx6 = idx_elem[8 * tid + 6]
    idx7 = idx_elem[8 * tid + 7]

    for i in range(6):
         fn0, fn1, fn2, fn3 = face_nodes_hex(i, idx0, idx1, idx2, idx3, idx4, idx5, idx6, idx7)
         # wp.printf("[%d]:%d = (%d,%d,%d,%d)\n", tid, i, fn0, fn1, fn2, fn3)
         tuple4 = wp.vec4i(fn0, fn1, fn2, fn3)
         ret = insert_hash4(array_tuple, array_offset, array_count, tuple4, map_size, count_mode)
         if ret != 0:
             err_code[0] = ret
             return

    err_code[0] = 0


@wp.kernel
def find_tris_tet_warp_kernel(idx_elem: wp.array(dtype=wp.int32),
                              array_tuple: wp.array(dtype=wp.vec3i),
                              array_offset: wp.array(dtype=wp.int32),
                              array_count: wp.array(dtype=wp.int32),
                              map_size: wp.int32,
                              external_tris: wp.array(dtype=wp.int32),
                              external_tris_idx: wp.array(dtype=wp.int32),
                              count_mode: wp.bool,
                              err_code: wp.array(dtype=wp.int32)
                              ):

    tid = wp.tid()
    idx0 = idx_elem[4 * tid + 0]
    idx1 = idx_elem[4 * tid + 1]
    idx2 = idx_elem[4 * tid + 2]
    idx3 = idx_elem[4 * tid + 3]

    for i in range(4):
         fn0, fn1, fn2 = face_nodes_tet(i, idx0, idx1, idx2, idx3)
         tuple3_sorted = sort3(fn0, fn1, fn2)
         idx_face = hash3(tuple3_sorted) % map_size
         face_counter = wp.int32(0)
         count = array_count[idx_face]
         map_idx = array_offset[idx_face]

         for i in range(count):
             check_tuple = array_tuple[map_idx+i]
             check_tuple_sorted = sort3(check_tuple[0], check_tuple[1], check_tuple[2])
             if check_tuple_sorted == tuple3_sorted:
                 face_counter += 1
                 continue
             else:
                 continue

         if face_counter == 0:
             wp.printf("ERROR[%d]: No matching face found (%d,%d,%d)\n", tid, fn0, fn1, fn2)
             err_code[0] = -2
             return

         elif face_counter == 1:
             tris_idx = wp.atomic_add(external_tris_idx, 0, 1)

             if (not count_mode) and 3*tris_idx+0 >= external_tris.shape[0]:
                 wp.printf("ERROR[%d]: Not enough storage for hull tris (%d v %d)\n", 3*tris_idx, external_tris.shape[0])
                 err_code[0] = -4
                 return

             if not count_mode:
                 external_tris[3*tris_idx+0] = fn0
                 external_tris[3*tris_idx+1] = fn1
                 external_tris[3*tris_idx+2] = fn2

         elif face_counter > 2:
             wp.printf("ERROR[%d]: Face matched more than twice: %d\n", tid, face_counter)
             err_code[0] = -3
             return

    err_code[0] = 0


@wp.kernel
def find_quads_hex_warp_kernel(idx_elem: wp.array(dtype=wp.int32),
                               array_tuple: wp.array(dtype=wp.vec4i),
                               array_offset: wp.array(dtype=wp.int32),
                               array_count: wp.array(dtype=wp.int32),
                               map_size: wp.int32,
                               external_quads: wp.array(dtype=wp.int32),
                               external_quads_idx: wp.array(dtype=wp.int32),
                               count_mode: wp.bool,
                               err_code: wp.array(dtype=wp.int32)
                               ):

    tid = wp.tid()
    idx0 = idx_elem[8 * tid + 0]
    idx1 = idx_elem[8 * tid + 1]
    idx2 = idx_elem[8 * tid + 2]
    idx3 = idx_elem[8 * tid + 3]
    idx4 = idx_elem[8 * tid + 4]
    idx5 = idx_elem[8 * tid + 5]
    idx6 = idx_elem[8 * tid + 6]
    idx7 = idx_elem[8 * tid + 7]

    for i in range(6):
         fn0, fn1, fn2, fn3 = face_nodes_hex(i, idx0, idx1, idx2, idx3, idx4, idx5, idx6, idx7)
         tuple4_sorted = sort4(fn0, fn1, fn2, fn3)
         idx_face = hash4(tuple4_sorted) % map_size
         face_counter = wp.int32(0)
         offset = array_count[idx_face]
         map_idx = array_offset[idx_face]

         for i in range(offset):
             check_tuple = array_tuple[map_idx+i]
             check_tuple_sorted = sort4(check_tuple[0], check_tuple[1], check_tuple[2], check_tuple[3])
             if check_tuple_sorted == tuple4_sorted:
                 face_counter += 1
                 continue
             else:
                 continue

         if face_counter == 0:
             wp.printf("ERROR[%d]: No matching face found (%d,%d,%d,%d)\n", tid, fn0, fn1, fn2, fn3)
             err_code[0] = -2
             return

         elif face_counter == 1:
             quads_idx = wp.atomic_add(external_quads_idx, 0, 1)

             if (not count_mode) and 4*quads_idx+0 >= external_quads.shape[0]:
                 wp.printf("ERROR[%d]: Not enough storage for hull quads (%d v %d)\n", 4*quads_idx, external_quads.shape[0])
                 err_code[0] = -4
                 return

             if not count_mode:
                 external_quads[4*quads_idx+0] = fn0
                 external_quads[4*quads_idx+1] = fn1
                 external_quads[4*quads_idx+2] = fn2
                 external_quads[4*quads_idx+3] = fn3
         elif face_counter > 2:
             wp.printf("ERROR[%d]: Face matched more than twice: %d\n", tid, face_counter)
             err_code[0] = -3
             return

    err_code[0] = 0

def find_quads_hex_warp(idx_elem):

    num_elements = idx_elem.shape[0]//8
    map_size = num_elements * 3
    print(f"num_elements={num_elements}")
    array_tuple = wp.zeros(1, dtype=wp.vec4i)
    array_offset = wp.zeros(map_size+1, dtype=wp.int32)
    array_count = wp.zeros(map_size, dtype=wp.int32)
    external_quads = wp.zeros(1, dtype=wp.int32)
    external_quads_idx = wp.zeros(1,dtype=wp.int32)
    err_code = wp.zeros(1,dtype=wp.int32)

    wp.launch(build_edges_occurance_hex_warp_kernel, num_elements,
              inputs=[idx_elem, array_tuple,
                      array_count, array_offset, map_size, wp.bool(True), err_code])

    array_offset_cp = cp.array(array_offset)
    cp.cumsum(cp.array(array_count), out=array_offset_cp[1:])

    num_map_entries = int(array_offset_cp.get()[-1])

    array_offset = wp.array(array_offset_cp, dtype=wp.int32)

    print(f"Memory usage: {(map_size*3*4 + num_map_entries*4*4)/1e9} GB")

    array_tuple = wp.zeros(num_map_entries, dtype=wp.vec4i)
    array_count = wp.zeros(map_size, dtype=wp.int32) # reset counter

    err_code = wp.zeros(1,dtype=wp.int32)

    wp.launch(build_edges_occurance_hex_warp_kernel, num_elements,
              inputs=[idx_elem, array_tuple,
                      array_count, array_offset, map_size, wp.bool(False), err_code])

    err = err_code.numpy()
    if err != 0:
        print(f"ERROR 'build_edges_occurance_hex_warp_kernel' code err={err}")
        print(f"array_offset={array_offset}")
        print(f"array_count={array_offset}")
        return np.array([],dtype=np.int32)

    wp.launch(find_quads_hex_warp_kernel, num_elements, inputs=[idx_elem, array_tuple,
                                                                array_offset, array_count, map_size,
                                                                external_quads, external_quads_idx,
                                                                True, err_code])
    err = err_code.numpy()
    if err != 0:
        print(f"ERROR 'find_quads_hex_warp_kernel' code err={err}")
        return np.array([],dtype=np.int32)
    num_quads = int(external_quads_idx.numpy()[0])

    print(f"Additional Memory usage: {(4*num_quads*4)/1e9} GB")

    external_quads = wp.zeros(4*num_quads, dtype=wp.int32)
    external_quads_idx = wp.zeros(1, dtype=wp.int32)
    wp.launch(find_quads_hex_warp_kernel, num_elements, inputs=[idx_elem, array_tuple,
                                                                array_offset, array_count, map_size,
                                                                external_quads, external_quads_idx,
                                                                False, err_code])
    if err != 0:
        print(f"ERROR 'find_quads_hex_warp_kernel' code err={err}")
        return np.array([],dtype=np.int32)

    return external_quads


def find_tris_tet_warp(idx_elem):

    num_elements = idx_elem.shape[0]//4
    map_size = num_elements * 3
    print(f"num_elements={num_elements}")
    array_tuple = wp.zeros(1, dtype=wp.vec3i)
    array_offset = wp.zeros(map_size+1, dtype=wp.int32)
    array_count = wp.zeros(map_size, dtype=wp.int32)
    external_tris = wp.zeros(1, dtype=wp.int32)
    external_tris_idx = wp.zeros(1,dtype=wp.int32)
    err_code = wp.zeros(1,dtype=wp.int32)

    wp.launch(build_edges_occurance_tet_warp_kernel, num_elements,
              inputs=[idx_elem, array_tuple,
                      array_count, array_offset, map_size, wp.bool(True), err_code])

    array_offset_cp = cp.array(array_offset)
    cp.cumsum(cp.array(array_count), out=array_offset_cp[1:])

    num_map_entries = int(array_offset_cp.get()[-1])

    array_offset = wp.array(array_offset_cp, dtype=wp.int32)

    print(f"Memory usage: {(map_size*4*3 + num_map_entries*4*3)/1e9} GB")

    array_tuple = wp.full(num_map_entries, value=wp.vec3i(-1,-1,-1), dtype=wp.vec3i)
    array_count = wp.zeros(map_size, dtype=wp.int32) # reset counter

    err_code = wp.zeros(1,dtype=wp.int32)

    wp.launch(build_edges_occurance_tet_warp_kernel, num_elements,
              inputs=[idx_elem, array_tuple,
                      array_count, array_offset, map_size, wp.bool(False), err_code])

    err = err_code.numpy()
    if err != 0:
        print(f"ERROR 'build_edges_occurance_tet_warp_kernel' code err={err}")
        print(f"array_offset={array_offset}")
        print(f"array_count={array_offset}")
        return np.array([],dtype=np.int32)

    wp.launch(find_tris_tet_warp_kernel, num_elements, inputs=[idx_elem, array_tuple,
                                                                array_offset, array_count, map_size,
                                                                external_tris, external_tris_idx,
                                                                True, err_code])
    err = err_code.numpy()
    if err != 0:
        print(f"ERROR 'find_tris_tet_warp_kernel' code err={err}")
        return np.array([],dtype=np.int32)
    num_tris = int(external_tris_idx.numpy()[0])

    print(f"Additional Memory usage: {(4*num_tris*3)/1e9} GB")

    external_tris = wp.full(3*num_tris, value=-1, dtype=wp.int32)
    external_tris_idx = wp.zeros(1, dtype=wp.int32)
    wp.launch(find_tris_tet_warp_kernel, num_elements, inputs=[idx_elem, array_tuple,
                                                                array_offset, array_count, map_size,
                                                                external_tris, external_tris_idx,
                                                                False, err_code])
    if err != 0:
        print(f"ERROR 'find_tris_tet_warp_kernel' code err={err}")
        return np.array([],dtype=np.int32)

    return external_tris





# @wp.kernel
# def face_counter(idx_elem, idx_counter):
#     tid = wp.tid()
#     wp.atomic_add(idx_counter, idx_elem[tid], 1)

# @wp.kernel
# def unique_face_gather(idx_counter, face_list, face_idx, count_mode=True):
#     tid = wp.tid()
#     face_count = idx_counter[tid]
#     if face_count == 1:
#         idx = wp.atomic_add(face_idx, 0, 1)
#         if not count_mode:
#             face_list[idx] = tid


# def find_faces(idx_elem):
#     idx_max = int(cp.max(cp.array(idx_elem)))
#     idx_counter = wp.zeros(idx_max, dtype=wp.int32)
#     wp.launch(face_counter, idx_max, inputs=[idx_elem, idx_counter])
#     face_list = wp.zeros(1, dtype=wp.int32)
#     face_idx = wp.zeros(1, dtype=wp.int32)
#     wp.launch(unique_face_gather, idx_max, inputs=[idx_counter, face_list, face_idx, True])
#     num_edge_faces = int(face_idx.numpy()[0])
#     face_list = wp.full(num_edge_faces, value=-1, dtype=wp.int32)
#     wp.launch(unique_face_gather, idx_max, inputs=[idx_counter, face_list, face_idx, False])

#     return face_list


# def combine_all_faces(faces, offsets):
    
#     num_faces = 0
#     [num_faces += offset.shape[0]-1 for offset in offsets]

#     # for (face, offset) in zip(faces, offsets):
        



def build_hull_elements_warp(idx_elem, mesh_type: str):

    if mesh_type == "TETRA_4":
        return find_tris_tet_warp(idx_elem)
    elif mesh_type == "HEXA_8":
        return find_quads_hex_warp(idx_elem)
    else:
        raise RuntimeError(f"Unsupported element type: {mesh_type}")

# pure python version for testing
def build_edges_occurance_hex(idx_hex):

    edges_occurance = {}
    num_normal = 0
    num_duplicated = 0
    num_elements = idx_hex.shape[0] // 8
    for tid in range(num_elements):
        if tid % 10000 == 0:
            print(f"Progress {tid/num_elements}")
        v0 = idx_hex[8 * tid + 0]
        v1 = idx_hex[8 * tid + 1]
        v2 = idx_hex[8 * tid + 2]
        v3 = idx_hex[8 * tid + 3]
        v4 = idx_hex[8 * tid + 4]
        v5 = idx_hex[8 * tid + 5]
        v6 = idx_hex[8 * tid + 6]
        v7 = idx_hex[8 * tid + 7]

        face0 = face_nodes_hex_(0, v0, v1, v2, v3, v4, v5, v6, v7)
        face1 = face_nodes_hex_(1, v0, v1, v2, v3, v4, v5, v6, v7)
        face2 = face_nodes_hex_(2, v0, v1, v2, v3, v4, v5, v6, v7)
        face3 = face_nodes_hex_(3, v0, v1, v2, v3, v4, v5, v6, v7)
        face4 = face_nodes_hex_(4, v0, v1, v2, v3, v4, v5, v6, v7)
        face5 = face_nodes_hex_(5, v0, v1, v2, v3, v4, v5, v6, v7)

        def e2o(face, edge_id):
            # Unify the quad's indices to be used as the lookup key
            face_ = tuple(sorted(face))
            if face_ in edges_occurance:
                # Already known, meaning this is not a hull/border face
                if edges_occurance[face_]:
                    edges_occurance[face_] = None
            else:
                # Not seen yet, store original face indicies (the unified
                # indices will not define a proper quad)
                edges_occurance[face_] = tuple(face)

        e2o(face0, 0)
        e2o(face1, 1)
        e2o(face2, 2)
        e2o(face3, 3)
        e2o(face4, 4)
        e2o(face5, 5)

    return edges_occurance

# pure python version for testing
def build_edges_occurance(idx_tet):

    edges_occurance = {}
    num_normal = 0
    num_duplicated = 0
    for tid in range(idx_tet.shape[0] // 4):
        idx0 = idx_tet[4 * tid + 0]
        idx1 = idx_tet[4 * tid + 1]
        idx2 = idx_tet[4 * tid + 2]
        idx3 = idx_tet[4 * tid + 3]

        tri0 = [idx0, idx2, idx1]
        tri1 = [idx0, idx1, idx3]
        tri2 = [idx0, idx3, idx2]
        tri3 = [idx1, idx2, idx3]

        # sanity checking
        if len(np.unique(np.array([idx0, idx1, idx2, idx3]))) < 4:
            if num_duplicated == 0:
                print(f"[{tid}]Duplicated vertex index! ({(idx0,idx1,idx2,idx3)})")
            num_duplicated += 1

        num_normal += 1

        tri0.sort()
        tri1.sort()
        tri2.sort()
        tri3.sort()

        def e2o(tri, edge_id):
            tri_ = (tri[0], tri[1], tri[2])
            if tri_ in edges_occurance:
                tids = edges_occurance[tri_]
                tids.append((tid, edge_id))
                # edges_occurance[tri_] = tids
            else:
                edges_occurance[tri_] = [(tid, edge_id)]

        e2o(tri0, 0)
        e2o(tri1, 1)
        e2o(tri2, 2)
        e2o(tri3, 3)

    return edges_occurance


def build_hull_triangles(edges_occurance):

    triangles = []

    for (k, v) in edges_occurance.items():

        if len(v) == 1:
            triangles.append(k[0])
            triangles.append(k[1])
            triangles.append(k[2])

    return np.array(triangles)


def build_hull_quads(edges_occurance):

    quads = []

    for face in edges_occurance.values():
        if face:
            quads.append(face[0])
            quads.append(face[1])
            quads.append(face[2])
            quads.append(face[3])

    return np.array(quads)


@wp.kernel
def compress_vertices_kernel(all_vertices: wp.array(dtype=wp.vec3f),
                             subset_vertices: wp.array(dtype=wp.vec3f),
                             old_indices: wp.array(dtype=wp.int32),
                             new_indices: wp.array(dtype=wp.int32),
                             mapping: wp.array(dtype=wp.int32),
                             idx: wp.array(dtype=wp.int32),
                             count_mode: wp.bool):

    tid = wp.tid()

    if tid >= old_indices.shape[0]:
        wp.printf("tid goes past indices (%d > %d)\n", tid, old_indices.shape[0])
        return
    if old_indices[tid] >= mapping.shape[0]:
        # wp.printf("indices goes past vertices (%d > %d)\n", old_indices[tid], mapping.shape[0])
        return

    if mapping[old_indices[tid]] == -1:
        i = idx[0]
        idx[0] += 1
        mapping[old_indices[tid]] = i
        if not count_mode:
            if i >= subset_vertices.shape[0]:
                wp.printf("i(%d) >= sv.size(%d)\n", i, subset_vertices.shape[0])
                return
            subset_vertices[i] = all_vertices[old_indices[tid]]
            new_indices[tid] = i
    else:
        if not count_mode:
            i = mapping[old_indices[tid]]
            new_indices[tid] = i



def compress_vertices(d_all_vertices, d_idx_elem):
    wp.set_device("cpu")
    all_vertices = d_all_vertices.to("cpu")
    idx_elem = d_idx_elem.to("cpu")

    subset_vertices = wp.zeros(0, dtype=wp.vec3f)
    new_indices = wp.full(idx_elem.shape[0], value=-1, dtype=idx_elem.dtype)
    mapping = wp.full(all_vertices.shape[0], value=-1, dtype=wp.int32)
    idx = wp.zeros(1, dtype=wp.int32)
    wp.launch(compress_vertices_kernel, idx_elem.shape[0],
              inputs=[all_vertices, subset_vertices, idx_elem, new_indices, mapping, idx, True],
              device='cpu')
    num_compressed_vertices = int(idx.numpy()[0])
    print(f"Compression results: Number of vertices - original {d_all_vertices.shape[0]} vs new {num_compressed_vertices}")

    subset_vertices = wp.zeros(num_compressed_vertices, dtype=wp.vec3f)
    mapping = wp.full(all_vertices.shape[0], value=-1, dtype=wp.int32)
    idx = wp.zeros(1, dtype=wp.int32)

    wp.launch(compress_vertices_kernel, idx_elem.shape[0],
              inputs=[all_vertices, subset_vertices, idx_elem, new_indices, mapping, idx, False],
              device='cpu')

    wp.set_device("cuda")

    return (subset_vertices.to("cuda"), new_indices.to("cuda"))

def hull_mesh_to_stage(vertices: np.array,
                       idx_elem: np.array,
                       idx_offset_maybe: np.array,
                       stage, parent_path, nodes_per_elem=3, hull_name="hull",
                       facet_limit=1000000):

    if isinstance(idx_offset_maybe, np.ndarray):
        num_facets = idx_offset_maybe.shape[0]
        # print(f"[{hull_name}] Num facets=", idx_offset_maybe.shape[0])
        if num_facets > facet_limit:
            print(f"Skipping {hull_name} because it has too many faces ({num_facets} > {facet_limit})")
            return

    hull_mesh = UsdGeom.Mesh.Define(stage, parent_path + "/" + hull_name)

    # print("triangulating vertices.shape=", vertices.shape)
    #vertices_gf3 = [
    #    Gf.Vec3f(float(vertices[i, 0]), float(vertices[i, 1]), float(vertices[i, 2])) for i in range(vertices.shape[0])
    #]

    vertices_vt = Vt.Vec3fArray.FromNumpy(vertices)
    idx_elem_vt = Vt.IntArray.FromNumpy(idx_elem)
    if isinstance(idx_offset_maybe, np.ndarray):
        idx_elem_count = Vt.IntArray.FromNumpy(idx_offset_maybe[1:] - idx_offset_maybe[:-1])
    else:
        idx_elem_count = Vt.IntArray.FromNumpy(nodes_per_elem * np.ones(idx_elem.shape[0] // nodes_per_elem))

    hull_mesh.GetPointsAttr().Set(vertices_vt)
    hull_mesh.GetFaceVertexIndicesAttr().Set(idx_elem_vt)
    hull_mesh.GetFaceVertexCountsAttr().Set(idx_elem_count)

    return hull_mesh


def generate_hull(idx_elem: wp.array(dtype=wp.int32), mesh_type: str, with_warp_and_cupy=True):

    print("TRYING TO TRIANGULATE HULL OF TYPE: ", mesh_type)

    if with_warp_and_cupy:
        idx_elem_hull = build_hull_elements_warp(idx_elem, mesh_type)
        # print("UNSUPPORTED!")
    else:
        if mesh_type == "TETRA_4":
            edge_occurances_np = build_edges_occurance(idx_elem.numpy())
            idx_elem_hull = wp.from_numpy(build_hull_triangles(edge_occurances_np))
        elif mesh_type == "HEXA_8":
            edge_occurances_np = build_edges_occurance_hex(idx_elem.numpy())
            idx_elem_hull = wp.from_numpy(build_hull_quads(edge_occurances_np))
            # idx_elem_hull = find_quads_hex_warp(idx_elem)
        else:
            raise RuntimeError(f"Unsupported element type: {mesh_type}")

    # if mesh_type == "TETRA_4":
    #     fix_triangle_hull_orientation(vertices, idx_elem_hull)

    return idx_elem_hull


def get_vertices_from_usd(stage_url, prim_path):

    from stage_reader import open_stage, return_array

    stage = open_stage(stage_url)
    prim = stage.GetPrimAtPath(prim_path)
    x = return_array(prim, "coordsXHdf5Path")
    y = return_array(prim, "coordsYHdf5Path")
    z = return_array(prim, "coordsZHdf5Path")
    return np.column_stack((x,y,z))


def get_idx_elem_from_usd(stage_url, prim_path):

    from stage_reader import open_stage, return_array

    stage = open_stage(stage_url)
    prim = stage.GetPrimAtPath(prim_path)
    return return_array(prim, "meshConnectivityHdf5Path")


if __name__ == "__main__":
    from vtk_writer import read_tetmesh_vtk, save_tetmesh_vtk
    import sys
    vertices = wp.array(
        [
            wp.vec3f(0.0, 0.0, 0.0),
            wp.vec3f(1.0, 0.0, 0.0),
            wp.vec3f(0.0, 1.0, 0.0),
            wp.vec3f(0.0, 0.0, 1.0),
            wp.vec3f(1.0, 1.0, 1.0),
        ],
        dtype=wp.vec3f,
    )

    idx_tet = wp.array([0, 1, 2, 3, 1, 2, 3, 4], dtype=wp.int32)
    
    edge_occurances_np = build_edges_occurance(idx_tet.numpy())

    idx_tri = wp.from_numpy(build_hull_triangles(edge_occurances_np))
    
    # print("idx_tri before=", idx_tri)
    # fix_triangle_hull_orientation(vertices, idx_tri)
    # print("idx_tri after=", idx_tri)

    # idx_tri2 = generate_hull(vertices, wp.array(idx_tet), "TETRA_4", with_warp_and_cupy=True)
    # print("new way before: ", idx_tri2)
    # fix_triangle_hull_orientation(vertices, idx_tri2)
    # print("new way: ", idx_tri2)

    # save_tetmesh_vtk(vertices.numpy(), idx_tet.numpy(), filename="tet_mesh")
    # save_tetmesh_vtk(vertices.numpy(), idx_tri_np=idx_tri.numpy(), filename="tri_mesh")

    vertices_hexes = wp.array(
        [
            # CGNS layout, see comment way up above
            wp.vec3f(1.0, 0.0, 0.0),
            wp.vec3f(1.0, 1.0, 0.0),
            wp.vec3f(0.0, 1.0, 0.0),
            wp.vec3f(0.0, 0.0, 0.0),

            wp.vec3f(1.0, 0.0, 1.0),
            wp.vec3f(1.0, 1.0, 1.0),
            wp.vec3f(0.0, 1.0, 1.0),
            wp.vec3f(0.0, 0.0, 1.0),

            wp.vec3f(2.0, 0.0, 0.0),
            wp.vec3f(2.0, 1.0, 0.0),
            wp.vec3f(2.0, 1.0, 1.0),
            wp.vec3f(2.0, 0.0, 1.0),

        ],
        dtype=wp.vec3f,
    )

    idx_hex = wp.array([0, 1, 2, 3,   4, 5, 6, 7,   8, 9, 1, 0,   11, 10, 5, 4], dtype=wp.int32)

    # eo_hex = build_edges_occurance_hex_numba(idx_hex.numpy())
    hull_hex = find_quads_hex_warp(idx_hex)

    edge_occurances_np = build_edges_occurance_hex(idx_hex.numpy())
    idx_elem_hull = wp.from_numpy(build_hull_quads(edge_occurances_np))

    print(f"warp_hex={hull_hex.numpy().reshape((10,4))}, python_hex={idx_elem_hull.reshape((10,4))}")

    idx_elem_pod = get_idx_elem_from_usd("/home/max/dev/cgns_work/data/pod2-ac50-60kw-x04.usd", "/World/Zone_1/Elem_Hexas")
    
    print("idx_pod:", idx_elem_pod)
    hull_pod_hex = generate_hull(wp.array(idx_elem_pod.astype(np.int32)), "HEXA_8")
    print(f"hull_pod_hex[{hull_pod_hex.shape[0]//4} quads]={hull_pod_hex.numpy()}")
    # hull_pod_hex_py = generate_hull(idx_elem_pod, "HEXA_8", with_warp_and_cupy=False)
    # print(f"hull_pod_hex[{hull_pod_hex_py.shape[0]//4} quads]={hull_pod_hex_py.numpy()}")


    idx_elem_yf17 = get_idx_elem_from_usd("/home/max/dev/cgns_work/data/yf17_from_extension.usda", "/World/Zone1/GridElements")
    yf17_xyz = get_vertices_from_usd("/home/max/dev/cgns_work/data/yf17_from_extension.usda", "/World/Zone1/GridElements")
    print("idx_yf17:", idx_elem_yf17)

    hull_yf17_wp = generate_hull(wp.array(idx_elem_yf17.astype(np.int32)), "TETRA_4")
    hull_yf17_py = generate_hull(wp.array(idx_elem_yf17.astype(np.int32)), "TETRA_4", with_warp_and_cupy=False)
    print("hull_yf17_tet=", hull_yf17_wp.numpy())

    save_tetmesh_vtk(yf17_xyz, idx_tri_np=hull_yf17_wp.numpy()-1, filename="yf17_hullmesh")

    a = np.array(hull_yf17_wp.numpy())
    print(f"Min values of tet indices={idx_elem_yf17.min()}, Min values of hull indices={a.min()}")
    print(f"Num tris py={hull_yf17_py.shape[0]//3} vs wp={hull_yf17_wp.shape[0]//3}")

    # idx_tri_wp = build_hull_triangles_warp(idx_tet)
    # print("idx_tri_wp before=", idx_tri_wp)
    # fix_triangle_hull_orientation(vertices, idx_tri_wp)
    # print("idx_tri_wp after=", idx_tri_wp)

    # verts_yf17_np, idx_tet_yf17_np = read_tetmesh_vtk("yf17_tetmesh.vtk")
    # verts_yf17 = wp.array(verts_yf17_np, dtype=wp.vec3f)
    # idx_tet_yf17 = wp.array(idx_tet_yf17_np, dtype=wp.int32)

    # _, idx_tri_yf17 = triangulate_hull(verts_yf17, idx_tet_yf17_np, with_warp_and_cupy=False)
    # _, idx_tri_yf17_warp = triangulate_hull(verts_yf17, idx_tet_yf17, with_warp_and_cupy=True)

    # save_tetmesh_vtk(verts_yf17_np, idx_tri_np=idx_tri_yf17_warp.numpy(), filename="yf17_trimesh")
