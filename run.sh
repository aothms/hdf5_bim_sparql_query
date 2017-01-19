echo "This script executes and compares sparql queries on building models."
read -n 1 -s -p "Press any key to continue...
"

SCRIPTPATH=$( cd $(dirname $0) ; pwd -P )
BUILDPATH="$SCRIPTPATH/build"
RESULTSFILE="$SCRIPTPATH/results.csv"
mkdir -p $BUILDPATH

if [ ! -f $BUILDPATH/setup ]; then

export CFLAGS="-O3 -march=native"
export CXXFLAGS="-O3 -march=native"


echo "Checking prerequisites"
for pkg in oracle-java8-installer g++ make maven git zip unzip
do
dpkg -s $pkg &> /dev/null && continue
echo "Missing dependencies, run:"
echo "sudo add-apt-repository ppa:webupd8team/java"
echo "sudo apt-get update"
echo "sudo apt-get install oracle-java8-installer g++ make maven git zip unzip python-pip"
echo "sudo python -m pip install --upgrade pip"
echo "sudo python -m pip install h5py==2.7.0rc2 pyparsing rdflib"
exit 1
done


echo "Obtaining jena"
cd $BUILDPATH
wget -qq http://apache.mirror.triple-it.nl/jena/binaries/apache-jena-3.1.1.tar.gz
tar -xf apache-jena-3.1.1.tar.gz


echo "Obtaining and building IFC to RDF"
cd $BUILDPATH
git clone -q https://github.com/mmlab/IFC-to-RDF-converter
cd IFC-to-RDF-converter/
git checkout -q 991c773
cd converter
mkdir classes
javac -nowarn -cp "lib/jena-3.0.0/*:lib/json/*" -d classes src/org/buildingsmart/*.java src/org/buildingsmart/vo/*.java src/fi/ni/rdf/Namespace.java src/fi/ni/gui/fx/*.java &> /dev/null
echo "Main-Class: org.buildingsmart.IfcReaderStream" > manifest.txt
echo "Class-Path:$(find lib -name "*.jar" | sed "s/$/ /g" | sed "s/^/ /g")" >> manifest.txt
jar cvfm IFC-to-RDF-converter.jar manifest.txt -C classes . &> /dev/null
cd data/
zip -qvu ../IFC-to-RDF-converter.jar * &> /dev/null


echo "Obtaining and building rdf3x"
cd $BUILDPATH
git clone -q https://github.com/gh-rdf3x/gh-rdf3x
cd gh-rdf3x
patch -p1 < $SCRIPTPATH/patches/rdf3xquery.diff
make -j &> /dev/null


echo "Obtaining and building hdt"
cd $BUILDPATH
git clone -q https://github.com/rdfhdt/hdt-java
cd hdt-java
mvn -q package &> /dev/null


echo "Building ARQ query executor"
cd $BUILDPATH
mkdir arq_query
cd arq_query
cp $SCRIPTPATH/arq_query/ArqQuery.java .
mkdir classes
javac -cp "../apache-jena-3.1.1/lib/*:../hdt-java/hdt-java-package/target/hdt-java-package-2.0-distribution/hdt-java-package-2.0/lib/*" -d classes ArqQuery.java
echo "Main-Class: ArqQuery" > manifest.txt
echo "Class-Path:$(find ../apache-jena-3.1.1/lib -name "*.jar" | sed "s/$/ /g" | sed "s/^/ /g")" >> manifest.txt
echo "$(find ../hdt-java/hdt-java-package/target/hdt-java-package-2.0-distribution/hdt-java-package-2.0/lib -name "*.jar" | sed "s/$/ /g" | sed "s/^/ /g")" >> manifest.txt
jar cvfm arq_query.jar manifest.txt -C classes . &> /dev/null


echo "Obtaining and building IfcOpenShell with HDF5 support"
cd $BUILDPATH
wget -qq http://downloads.sourceforge.net/project/boost/boost/1.63.0/boost_1_63_0.tar.gz
tar -xf boost_1_63_0.tar.gz
wget -qq https://downloads.sourceforge.net/project/libpng/zlib/1.2.11/zlib-1.2.11.tar.gz
tar -xf zlib-1.2.11.tar.gz
cd zlib-1.2.11/
./configure --prefix=$BUILDPATH/zlib-1.2.11/install &> /dev/null
make -j install &> /dev/null
cd $BUILDPATH
wget -qq https://support.hdfgroup.org/ftp/HDF5/current18/src/hdf5-1.8.18.tar.gz
tar -xf hdf5-1.8.18.tar.gz
cd hdf5-1.8.18/
./configure --enable-cxx --enable-production --with-zlib=$BUILDPATH/zlib-1.2.11/install &> /dev/null
make -j install &> /dev/null
cd $BUILDPATH
git clone -q https://github.com/ISBE-TUe/IfcOpenShell-HDF5
cd IfcOpenShell-HDF5
patch -s -p1 < $SCRIPTPATH/hdf5_convert/ifcopenshell.patch
mkdir bin
cd src
mkdir hdf5_convert
cd hdf5_convert
cp $SCRIPTPATH/hdf5_convert/hdf5_convert.cpp main.cpp
g++ -O3 -march=native -o ../../bin/ifc_hdf5_convert -DBOOST_OPTIONAL_USE_OLD_DEFINITION_OF_NONE -std=c++11 -I$BUILDPATH/boost_1_63_0/ -I$BUILDPATH/hdf5-1.8.18/hdf5/include main.cpp ../ifcparse/*.cpp $BUILDPATH/hdf5-1.8.18/hdf5/lib/libhdf5_cpp.a $BUILDPATH/hdf5-1.8.18/hdf5/lib/libhdf5.a -ldl $BUILDPATH/zlib-1.2.11/install/lib/libz.a


echo "Obtaining IfcOpenShell-python"
cd $BUILDPATH
wget -qq -O ifcopenshell-python.zip wget http://sourceforge.net/projects/ifcopenshell/files/0.5.0-preview1/ifcopenshell-python-2.7-0.5.0-preview1-linux64.zip/download
unzip -qq ifcopenshell-python.zip
PYTHON_MODULE_DIR=`python -c "import site; print site.getusersitepackages()"`
mkdir -p $PYTHON_MODULE_DIR
mv ifcopenshell $PYTHON_MODULE_DIR


echo "Obtaining test files"
cd $SCRIPTPATH
mkdir files
cd files
wget -qq -O duplex.zip http://projects.buildingsmartalliance.org/files/?artifact_id=4278
wget -qq -O office.zip http://projects.buildingsmartalliance.org/files/?artifact_id=4284
wget -qq -O clinic.zip http://projects.buildingsmartalliance.org/files/?artifact_id=4289
wget -qq -O riverside.zip http://download2cf.nemetschek.net/www_misc/bim/DCR-LOD_300.zip
unzip -qq "*.zip"
mkdir duplex clinic office riverside
mv Duplex_A_20110907_optimized.ifc duplex/duplex.ifc
mv Office_A_20110811.ifc office/office.ifc
mv Clinic_MEP_20110906_optimized.ifc clinic/clinic.ifc
mv Architectural/DC_Riverside_Bldg-LOD_300.ifc riverside/riverside.ifc



touch $BUILDPATH/setup
fi

MEM=`grep MemTotal /proc/meminfo | awk '{print int($2/1000000)}'`
echo "JVM_ARGS=-Xmx${MEM}g $BUILDPATH"'/apache-jena-3.1.1/bin/riot --out=nt $1 > $2' > $BUILDPATH/riot.sh
echo "JVM_ARGS=-Xmx${MEM}g $BUILDPATH"'/apache-jena-3.1.1/bin/sparql --data=$1 --query=$2' > $BUILDPATH/query_jena.sh
echo "java -Xmx${MEM}g -jar $BUILDPATH"'/arq_query/arq_query.jar $1 $2' > $BUILDPATH/query_arq.sh
echo "JVM_ARGS=-Xmx${MEM}g $BUILDPATH"'/apache-jena-3.1.1/bin/tdbquery --loc=$1 --query=$2' > $BUILDPATH/query_tdb.sh

convert_to_rdf="java -Xmx${MEM}g -jar $BUILDPATH/IFC-to-RDF-converter/converter/IFC-to-RDF-converter.jar"
convert_to_nt="/bin/sh $BUILDPATH/riot.sh"
convert_to_rdf3x="$BUILDPATH/gh-rdf3x/bin/rdf3xload"
convert_to_tdb="$BUILDPATH/apache-jena-3.1.1/bin/tdbloader -loc"
convert_to_hdt="$BUILDPATH/hdt-java/hdt-java-package/target/hdt-java-package-2.0-distribution/hdt-java-package-2.0/bin/rdf2hdt.sh"
convert_to_hdf5="$BUILDPATH/IfcOpenShell-HDF5/bin/ifc_hdf5_convert"

query_jena="/bin/sh $BUILDPATH/query_jena.sh"
query_arq="/bin/sh $BUILDPATH/query_arq.sh"
query_tdb="/bin/sh $BUILDPATH/query_tdb.sh"
query_rdf3x="$BUILDPATH/gh-rdf3x/bin/rdf3xquery"
query_hdf5="python $SCRIPTPATH/src/run_query.py"

function trace_bytes_read() {
    strace -f -s0 -etrace=read $1 2>&1 >/dev/null | grep read | awk 'BEGIN {FS="="}{ sum += $2} END {print sum}'
}

function trace_bytes_written() {
    strace -f -s0 -etrace=write $1 2>&1 >/dev/null | grep write | awk 'BEGIN {FS="="}{ sum += $2} END {print sum}'
}

function trace_mem_usage() {
    /usr/bin/time -v $1 2>&1 >/dev/null | grep "Maximum resident" | cut -c38-
}

function min_value() {
    printf "%s\n" "$@" | sort -g | head -n1
}

function trace_time() {
    TIMEFORMAT="TIME=%3R,%3U,%3S"
    times=""
    for i in 0 1 2; do
        t=$( { time $1 &>/dev/null ; } 2>&1 )
        >&2 echo "measured time [$i] (real, user, system) $t"
        times="$times `echo $t | grep TIME= | cut -c6-`"
        if [ "$FULL_BENCHMARK" = "0" ]; then
        break
        fi
    done
    echo `min_value $times`
}

function capture_reported_time() {
    times=""
    for i in 0 1 2; do
        results=`$1 2>&1 1>/dev/null`
        pt=`echo "$results" | grep "Parse time" | cut -c 13- | sed 's/....$//'`
        qt=`echo "$results" | grep "Query time" | cut -c 13- | sed 's/....$//'`
        t="$qt,$pt"
        >&2 echo "reported time [$i] (query, parse) $t"
        times="$times $t"
        if [ "$FULL_BENCHMARK" = "0" ]; then
        break
        fi
    done
    echo `min_value $times`
}

function trace() {
    if [ "$FULL_BENCHMARK" = "1" ]; then    
    >&2 echo "$1"
    >&2 echo "$2"
    br=`trace_bytes_read "$2"`
    >&2 echo "bytes read $br"
    bw=`trace_bytes_written "$2"`
    >&2 echo "bytes written $bw"
    tt=`capture_reported_time "$2"`
    fi
    
    m=`trace_mem_usage "$2"`
    >&2 echo "mem usage $m"
    t=`trace_time "$2"`
    echo $1,$br,$m,$bw,$t,$tt >> $RESULTSFILE
}

FULL_BENCHMARK=0

echo "Converting models"

for model in duplex clinic office riverside
do
    cd $SCRIPTPATH/files/$model
    trace "convert_to_rdf,$model,"   "$convert_to_rdf $model.ifc $model.ttl"
    trace "convert_to_nt,$model,"    "$convert_to_nt $model.ttl $model.nt"
    trace "convert_to_rdf3x,$model," "$convert_to_rdf3x $model.rdf3x $model.nt"
    trace "convert_to_tdb,$model,"   "$convert_to_tdb tdb $model.nt"
    trace "convert_to_hdt,$model,"   "$convert_to_hdt $model.nt $model.hdt"
    trace "convert_to_hdf5,$model,"  "$convert_to_hdf5 $model.ifc $model.hdf5"
done

FULL_BENCHMARK=1

echo "Executing queries"

for model in duplex clinic office riverside
do
    cd $SCRIPTPATH/files/$model
    for query in $SCRIPTPATH/queries/q*.txt
    do 
        python $SCRIPTPATH/src/query_expand.py $query $query.expanded
        trace "query_jena_nt,$model,`basename $query`" "$query_arq $model.nt $query"
        # trace "query_jena_official_nt,$model,`basename $query`" "$query_jena $model.nt $query"
        # trace "query_jena_ttl,$model,`basename $query`" "$query_arq $model.ttl $query"
        trace "query_hdt,$model,`basename $query`" "$query_arq $model.hdt $query"
        # trace "query_tdb_official,$model,`basename $query`" "$query_tdb tdb $query"
        trace "query_tdb,$model,`basename $query`" "$query_arq tdb $query"
        trace "query_rdf3x,$model,`basename $query`" "$query_rdf3x $model.rdf3x $query.expanded"
        trace "query_hdf5,$model,`basename $query`" "$query_hdf5 $model.hdf5 $query"
    done
    
    cd $SCRIPTPATH/files
    du -ad1 duplex office clinic riverside > ../filesizes.txt
done


for model in duplex clinic office riverside
do
    cd $SCRIPTPATH/files/$model
    # This is an horribly slow way to calculate the amount of instances, but it is the only thing the preview1 wrapper provided
    NUM_INSTANCES=`python -c "import ifcopenshell; f = ifcopenshell.open('$model.ifc'); print len(f.wrapped_data.entity_names())"`
    echo $model,$NUM_INSTANCES >> ../../instances.csv
done
