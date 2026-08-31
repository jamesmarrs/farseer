# The following variables contains the files used by the different stages of the build process.
set(farseer_default_default_XC8_FILE_TYPE_assemble)
set_source_files_properties(${farseer_default_default_XC8_FILE_TYPE_assemble} PROPERTIES LANGUAGE ASM)

# For assembly files, add "." to the include path for each file so that .include with a relative path works
foreach(source_file ${farseer_default_default_XC8_FILE_TYPE_assemble})
        set_source_files_properties(${source_file} PROPERTIES INCLUDE_DIRECTORIES "$<PATH:NORMAL_PATH,$<PATH:REMOVE_FILENAME,${source_file}>>")
endforeach()

set(farseer_default_default_XC8_FILE_TYPE_assemblePreprocess)
set_source_files_properties(${farseer_default_default_XC8_FILE_TYPE_assemblePreprocess} PROPERTIES LANGUAGE ASM)

# For assembly files, add "." to the include path for each file so that .include with a relative path works
foreach(source_file ${farseer_default_default_XC8_FILE_TYPE_assemblePreprocess})
        set_source_files_properties(${source_file} PROPERTIES INCLUDE_DIRECTORIES "$<PATH:NORMAL_PATH,$<PATH:REMOVE_FILENAME,${source_file}>>")
endforeach()

set(farseer_default_default_XC8_FILE_TYPE_compile
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../bg95.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../gps.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../main.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../telemetry.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../timer.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../uart1.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../uart2.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../uart3.c")
set_source_files_properties(${farseer_default_default_XC8_FILE_TYPE_compile} PROPERTIES LANGUAGE C)
set(farseer_default_default_XC8_FILE_TYPE_link)
set(farseer_default_image_name "default.elf")
set(farseer_default_image_base_name "default")

# The output directory of the final image.
set(farseer_default_output_dir "${CMAKE_CURRENT_SOURCE_DIR}/../../../out/farseer")

# The full path to the final image.
set(farseer_default_full_path_to_image ${farseer_default_output_dir}/${farseer_default_image_name})

# Potential output file extensions
set(output_extensions
    .hex
    .hxl
    .mum
    .o
    .sdb
    .sym
    .cmf)
list(TRANSFORM output_extensions PREPEND "${farseer_default_output_dir}/${farseer_default_image_base_name}")
