# Additional clean files
cmake_minimum_required(VERSION 3.16)

if("${CONFIG}" STREQUAL "" OR "${CONFIG}" STREQUAL "")
  file(REMOVE_RECURSE
  "/Users/james/motorsports/projects/farseer/out/farseer/default.cmf"
  "/Users/james/motorsports/projects/farseer/out/farseer/default.hex"
  "/Users/james/motorsports/projects/farseer/out/farseer/default.hxl"
  "/Users/james/motorsports/projects/farseer/out/farseer/default.mum"
  "/Users/james/motorsports/projects/farseer/out/farseer/default.o"
  "/Users/james/motorsports/projects/farseer/out/farseer/default.sdb"
  "/Users/james/motorsports/projects/farseer/out/farseer/default.sym"
  )
endif()
