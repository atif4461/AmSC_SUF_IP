


find_package(Hddm REQUIRED)

add_library(hddm_r hddm_r++.cpp)
#target_link_libraries(hddm_r PUBLIC hddm)
target_include_directories(hddm_r PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>)
target_include_directories(hddm_r PUBLIC $<INSTALL_INTERFACE:include/amsc>)
install(TARGETS hddm_r LIBRARY DESTINATION lib)
install(FILES hddm_r.hpp DESTINATION include/amsc)

#find_package(Python REQUIRED COMPONENTS Development)

#add_library(_hddm_r pyhddm_r.cpp)
#target_link_libraries(_hddm_r PRIVATE Python::Python)
#install(TARGETS _hddm_r LIBRARY DESTINATION amsc/hddm_r_to_pandas)

find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_hddm_r pyhddm_r.cpp)
target_link_libraries(_hddm_r PRIVATE hddm_r)
install(TARGETS _hddm_r LIBRARY DESTINATION amsc/hddm_r_to_pandas)
