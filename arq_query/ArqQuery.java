import java.io.File;
import java.io.IOException;

import org.apache.jena.query.QueryExecution;
import org.apache.jena.query.QueryExecutionFactory;
import org.apache.jena.query.ResultSet;
import org.apache.jena.query.ResultSetFormatter;
import org.apache.jena.query.ReadWrite;
import org.apache.jena.rdf.model.Model;
import org.apache.jena.rdf.model.ModelFactory;

import org.apache.jena.riot.RDFDataMgr;

import org.rdfhdt.hdt.hdt.HDT;
import org.rdfhdt.hdt.hdt.HDTManager;
import org.rdfhdt.hdtjena.HDTGraph;

import org.apache.jena.query.QueryFactory;
import org.apache.jena.query.Query;
import org.apache.jena.query.Syntax;
import org.apache.jena.query.Dataset;
import org.apache.jena.query.DatasetFactory;

import org.apache.jena.tdb.TDBFactory;


public class ArqQuery {

    public static void main(String[] args) {
        if (args.length != 2) {
            System.out.println("Usage: arq_query <model_file> <query_file>");
            return;
        }
        
        final String model_name = args[0];
        final String query_name = args[1];
        
        final long tp0 = System.nanoTime();
        final Dataset ds;
        try {
            if (model_name.endsWith(".hdt")) {
                HDT hdt = HDTManager.mapIndexedHDT(model_name, null);
                // Create Jena Model on top of HDT.
                HDTGraph graph = new HDTGraph(hdt);
                final Model model = ModelFactory.createModelForGraph(graph);
                ds = DatasetFactory.create(model);
            } else if (model_name.endsWith(".ttl") || model_name.endsWith(".nt")) {
                ds = DatasetFactory.create();
                final String file_uri = new File(model_name).toURI().toURL().toString();
                ds.begin(ReadWrite.WRITE);
                RDFDataMgr.read(ds, file_uri);
                ds.commit();
                ds.end();
            } else {
                ds = TDBFactory.createDataset(model_name);
            }
        } catch (IOException e) {
            e.printStackTrace();
            return;
        }
        final long tp1 = System.nanoTime();
    
        Query query = QueryFactory.read(query_name, null, Syntax.syntaxARQ) ;
        
        final long tq0 = System.nanoTime();
        QueryExecution qe = QueryExecutionFactory.create(query, ds);
        ResultSet results = qe.execSelect();
        final long tq1 = System.nanoTime();
        ResultSetFormatter.out(results);
        
        System.err.println(String.format("Parse time: %1$.3f sec", (float) (tp1 - tp0) / 1000000000f));
        System.err.println(String.format("Query time: %1$.3f sec", (float) (tq1 - tq0) / 1000000000f));
    }

}
