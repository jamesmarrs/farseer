include("${CMAKE_CURRENT_LIST_DIR}/rule.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/file.cmake")

set(farseer_default_library_list )

# Handle files with suffix (s|as|asm|AS|ASM|As|aS|Asm), for group default-XC8
if(farseer_default_default_XC8_FILE_TYPE_assemble)
add_library(farseer_default_default_XC8_assemble OBJECT ${farseer_default_default_XC8_FILE_TYPE_assemble})
    farseer_default_default_XC8_assemble_rule(farseer_default_default_XC8_assemble)
    list(APPEND farseer_default_library_list "$<TARGET_OBJECTS:farseer_default_default_XC8_assemble>")

endif()

# Handle files with suffix S, for group default-XC8
if(farseer_default_default_XC8_FILE_TYPE_assemblePreprocess)
add_library(farseer_default_default_XC8_assemblePreprocess OBJECT ${farseer_default_default_XC8_FILE_TYPE_assemblePreprocess})
    farseer_default_default_XC8_assemblePreprocess_rule(farseer_default_default_XC8_assemblePreprocess)
    list(APPEND farseer_default_library_list "$<TARGET_OBJECTS:farseer_default_default_XC8_assemblePreprocess>")

endif()

# Handle files with suffix [cC], for group default-XC8
if(farseer_default_default_XC8_FILE_TYPE_compile)
add_library(farseer_default_default_XC8_compile OBJECT ${farseer_default_default_XC8_FILE_TYPE_compile})
    farseer_default_default_XC8_compile_rule(farseer_default_default_XC8_compile)
    list(APPEND farseer_default_library_list "$<TARGET_OBJECTS:farseer_default_default_XC8_compile>")

endif()


# Main target for this project
add_executable(farseer_default_image_bs5gNqh4 ${farseer_default_library_list})

set_target_properties(farseer_default_image_bs5gNqh4 PROPERTIES
    OUTPUT_NAME "default"
    SUFFIX ".elf"
    ADDITIONAL_CLEAN_FILES "${output_extensions}"
    RUNTIME_OUTPUT_DIRECTORY "${farseer_default_output_dir}")
target_link_libraries(farseer_default_image_bs5gNqh4 PRIVATE ${farseer_default_default_XC8_FILE_TYPE_link})

# Add the link options from the rule file.
farseer_default_link_rule( farseer_default_image_bs5gNqh4)


