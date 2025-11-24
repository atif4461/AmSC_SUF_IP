
cmake_minimum_required(VERSION 3.16)
cmake_policy(SET CMP0074 NEW) # find_package() uses <PackageName>_ROOT implicit hints
project(amsc_expedition VERSION 0.0.1)

set (CMAKE_CXX_STANDARD 20)

# Add library directories to RPATH for all targets
set( CMAKE_SKIP_BUILD_RPATH FALSE )
set( CMAKE_BUILD_WITH_INSTALL_RPATH FALSE )
set( CMAKE_INSTALL_RPATH "${CMAKE_INSTALL_PREFIX}/lib;${CMAKE_INSTALL_PREFIX}/lib/JANA/plugins" )
set( CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE )

# Generate a compilation database, e.g. for IDE autocompletion
set( CMAKE_EXPORT_COMPILE_COMMANDS TRUE )

include(CTest)
add_subdirectory(hepnp_to_arrow)

