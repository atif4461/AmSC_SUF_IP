
cmake_minimum_required(VERSION 3.18)
project(amsc_expedition VERSION 2026.01.00)
set(CMAKE_EXPORT_COMPILE_COMMANDS TRUE)
set(CMAKE_POSITION_INDEPENDENT_CODE TRUE)

enable_testing()

add_subdirectory(src/cpp)
add_subdirectory(tests/cpp)
