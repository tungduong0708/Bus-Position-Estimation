from Graph import *
import time
import folium
import gmplot
import osmnx as ox

if __name__ == "__main__":
    print("Starting Bus Position Estimation Program...")
    graph = Graph()
    graph.build_graph()
    t1 = time.time()
    # graph.get_most_occuring_edge_between_file((5797649971, 377085386), (5042481760, 5042481759))
    graph.query_all_pairs_edges()
    # graph.preprocess_bus()
    # graph.retrieve_edge_matrix([(5797649971, 377085386)])
    t2 = time.time()
    print(f"Execution time: {t2 - t1}")

    # There are 174400 nodes, 205802 edges, 532 duplicate edges in  graph.
    # There are 17729 edges, 12594 trips, 11444 duplicate trips in bus graph.
    # 159.32140183448792

  