cmake_minimum_required(VERSION 3.19)

project(openmp_rpc_legacy_gap_fixture LANGUAGES CXX VERSION 0.1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(OMP_SDK_DIR "" CACHE PATH "Path to a local open.mp SDK checkout")
if(NOT OMP_SDK_DIR)
	foreach(candidate
		"/home/chairman/Projects/omp-ipv6/open.mp/SDK"
		"/home/chairman/Projects/LastBedStanding/deps/omp-sdk")
		if(EXISTS "${candidate}/include/sdk.hpp")
			set(OMP_SDK_DIR "${candidate}")
			break()
		endif()
	endforeach()
endif()

if(NOT EXISTS "${OMP_SDK_DIR}/include/sdk.hpp")
	message(FATAL_ERROR "OMP_SDK_DIR must contain include/sdk.hpp")
endif()
if(NOT CMAKE_SIZEOF_VOID_P EQUAL 4)
	message(FATAL_ERROR "The local open.mp server requires an i386 component")
endif()

add_subdirectory("${OMP_SDK_DIR}" "${CMAKE_BINARY_DIR}/omp-sdk" EXCLUDE_FROM_ALL)
add_library(rpc_legacy_gap_fixture SHARED src/rpc_legacy_gap_fixture.cpp)
target_link_libraries(rpc_legacy_gap_fixture PRIVATE OMP-SDK)
target_include_directories(rpc_legacy_gap_fixture SYSTEM PRIVATE
	"${OMP_SDK_DIR}/include"
	"${OMP_SDK_DIR}/lib/glm/glm/.."
	"${OMP_SDK_DIR}/lib/robin-hood-hashing/src/include"
	"${OMP_SDK_DIR}/lib/span-lite/include"
	"${OMP_SDK_DIR}/lib/string-view-lite/include")
target_compile_options(rpc_legacy_gap_fixture PRIVATE
	$<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-m32;-Wall;-Wextra;-Wpedantic;-Werror>)
target_link_options(rpc_legacy_gap_fixture PRIVATE
	$<$<LINK_LANG_AND_ID:CXX,GNU,Clang>:-m32>)
set_target_properties(rpc_legacy_gap_fixture PROPERTIES
	PREFIX ""
	OUTPUT_NAME "rpc_legacy_gap_fixture"
	POSITION_INDEPENDENT_CODE ON
	CXX_VISIBILITY_PRESET hidden
	VISIBILITY_INLINES_HIDDEN YES)
