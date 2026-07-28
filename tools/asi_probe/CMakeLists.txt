cmake_minimum_required(VERSION 3.20)

project(samp_probe_asi C)

include(CTest)

add_library(samp_probe MODULE
  src/samp_probe_asi.c
  src/samp_probe_death_cleanup.c
  src/samp_probe_pickup.c
  src/samp_probe_ui_latches.c
)

set_target_properties(samp_probe PROPERTIES
  PREFIX ""
  SUFFIX ".asi"
  OUTPUT_NAME "samp_probe"
)

target_compile_definitions(samp_probe PRIVATE
  WIN32_LEAN_AND_MEAN
)

if(MINGW)
  target_compile_options(samp_probe PRIVATE
    -Wall
    -Wextra
    -Wno-cast-function-type
    $<$<CONFIG:Debug>:-O0>
    $<$<CONFIG:Debug>:-g3>
    $<$<CONFIG:Debug>:-ggdb>
    $<$<CONFIG:RelWithDebInfo>:-g3>
    $<$<CONFIG:RelWithDebInfo>:-ggdb>
    $<$<CONFIG:Release>:-fno-asynchronous-unwind-tables>
    $<$<CONFIG:Release>:-fno-unwind-tables>
    $<$<CONFIG:Release>:-fno-ident>
  )

  target_link_options(samp_probe PRIVATE
    -Wl,--subsystem,windows
    -Wl,--exclude-all-symbols
    -Wl,-Map,$<TARGET_FILE_DIR:samp_probe>/samp_probe.map
    -static-libgcc
  )
endif()

if(BUILD_TESTING)
  find_package(Python3 COMPONENTS Interpreter QUIET)
  if(Python3_Interpreter_FOUND)
    add_test(
      NAME samp_probe_death_cleanup_exit_source_contract
      COMMAND
        ${Python3_EXECUTABLE}
        ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_death_cleanup_exit_source_contract.py
    )
  endif()
endif()
