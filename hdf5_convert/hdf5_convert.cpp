#include "../ifcparse/IfcFile.h"
#include "../ifcparse/Hdf5Settings.h"

int main(int argc, char** argv) {
    if (argc != 3) return 1;
    IfcParse::IfcFile f;
    if (!f.Init(argv[1])) return 1;

    IfcParse::Hdf5Settings settings;
    settings.compress() = true;
    settings.fix_cartesian_point() = true;
    settings.fix_global_id() = true;
    settings.instantiate_inverse() = true;
    settings.instantiate_select() = false;
    settings.chunk_size() = 2048;

    f.write_hdf5(argv[2], settings);

    return 0;
}
