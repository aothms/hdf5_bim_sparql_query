#include <cstring>
#include <time.h>

#include <H5Cpp.h>

// Timing utility macros
#define time(x) (clock_gettime(CLOCK_MONOTONIC_RAW, &x));
#define time_diff(x, y) (y.tv_sec-x.tv_sec + (y.tv_nsec-x.tv_nsec) / 1000000000.f)

double get_largest_window_hdf(const char* const filename) {
    H5::H5File file(filename, H5F_ACC_RDONLY);
    H5::DataSet dset = file.openDataSet("population/IfcWindow_instances");
    H5::CompType ct = dset.getCompType();
    const size_t instance_size = ct.getSize();
    H5::CompType ct_to_read = H5::CompType(instance_size);

    const char* member_names[] = {"set_unset_bitmap", "OverallWidth", "OverallHeight"};
    size_t offsets[3];

    for (int i = 0; i < 3; ++i) {
        int idx = ct.getMemberIndex(member_names[i]);
        H5::DataType dt = ct.getMemberDataType(idx);
        ct_to_read.insertMember(member_names[i], offsets[i] = ct.getMemberOffset(idx), dt);
        dt.close();
    }

    hsize_t dims;
    H5::DataSpace dspace = dset.getSpace();
    dspace.getSimpleExtentDims(&dims);
    dspace.close();

    uint8_t* buffer = new uint8_t[dims * instance_size];
    // Does not seem to be a big difference with {ct} and {ct_to_read}.
    dset.read(buffer, ct_to_read);

    uint16_t mask = (1 << 7) | (1 << 8);

    double d;

    double m = 0;
    for (size_t i = 0; i < dims; ++i) {
        uint8_t* inst = buffer + i * instance_size;
        uint16_t set_unset_bitmap = *((uint16_t*) inst + offsets[0]);
        if (set_unset_bitmap & mask) {
            memcpy(&d, inst + offsets[1], sizeof(double));
            double OverallWidth = d;
            memcpy(&d, inst + offsets[2], sizeof(double));
            double OverallHeight = d;
            double a = OverallWidth * OverallHeight;
            if (a > m) {
                m = a;
            }
        }
    }

    ct.close();
    dset.close();
    file.close();

    return m;
}


int main(int argc, char** argv) {
    const char* const hdf_filename = argv[1];

    timespec t0, t1;
    time(t0);
    double size = get_largest_window_hdf(hdf_filename);
    time(t1);

    printf("largest window size: %f\n", size);
    printf("time spent: %.5f\n", time_diff(t0, t1));
}
