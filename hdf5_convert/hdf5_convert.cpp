#include "../ifcparse/IfcFile.h"
#include "../ifcparse/Hdf5Settings.h"

#include <boost/lexical_cast.hpp>

int main(int argc, char** argv) {
    if (argc != 3 && argc != 4) return 1;
    IfcParse::IfcFile f;
    if (!f.Init(argv[1])) return 1;
    
    int chunk_size = 2048;
    if (argc == 4) {
        chunk_size = boost::lexical_cast<int>(argv[2]);
    }

    IfcParse::Hdf5Settings settings;
    settings.compress() = true;
    settings.fix_cartesian_point() = true;
    settings.fix_global_id() = true;
    settings.instantiate_inverse() = true;
    settings.instantiate_select() = false;
    settings.chunk_size() = chunk_size;

    f.write_hdf5(argv[2], settings);

    return 0;
}
