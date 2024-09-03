import osmium
import json
import time
import math
import ast
from folium.plugins import FastMarkerCluster
from folium.plugins import MarkerCluster
import numpy as np
import networkx as nx
from collections import defaultdict
from itertools import combinations
from tqdm import tqdm

class HighwayHandler(osmium.SimpleHandler):
    def __init__(self):
        super(HighwayHandler, self).__init__()
        self.highways = {}

    def way(self, w):
        if 'highway' in w.tags:
            self.highways[w.id] = {
                'id': w.id,
                'nodes': [n.ref for n in w.nodes],
                'tags': {tag.k: tag.v for tag in w.tags}
            }

class Graph():
    def __init__(self) -> None:
        self.G = nx.MultiDiGraph()
        self.edges = defaultdict(lambda: defaultdict(tuple))
        self.bus_trips = {}
        self.bus_edges = set()
        self.edge_to_trips = defaultdict(set)
        self.edge_matrix = defaultdict(lambda: defaultdict(list))
        self.edge_pos = defaultdict(lambda: defaultdict(int))

    def build_graph(self, osm_file="HoChiMinh.osm"):
        print(f"Reading {osm_file} file...")
        handler = HighwayHandler()
        handler.apply_file(osm_file)

        for way_id, way in tqdm(handler.highways.items(), desc="Making graph"):
            oneway = way['tags'].get('oneway') == 'yes'
            source_node = way['nodes'][0]
            target_node = way['nodes'][-1]

            self.G.add_edge(source_node, target_node, id=way['id'], sub_nodes=way['nodes'])
            if not oneway:
                self.G.add_edge(target_node, source_node, id=way['id'], sub_nodes=way['nodes'][::-1])

        print(f"There are {self.G.number_of_nodes()} nodes, {self.G.number_of_edges()} edges.")

    def preprocess_graph(self):
        for edge in tqdm(self.G.edges(data=True), total=len(list(self.G.edges)), desc="Preprocessing graph"):
            source, target, data = edge
            sub_nodes = data['sub_nodes']
            for u, v in zip(sub_nodes, sub_nodes[1:]):
                self.edges[str(u)][str(v)] = (source, target)

    def preprocess_bus(self):
        trip_id = 0
        with open('bus-history.json', 'r', encoding='utf-8') as f:
            for line in  tqdm(f, total=3347, desc="Preprocessing trips"):
                json_object = json.loads(line)
                for trip in json_object['tripList']:
                    if not trip['edgesOfPath2']:
                        continue
                    
                    self.bus_trips[trip_id] = []
                    edge_id = 0
                    for sub_edge in trip['edgesOfPath2']:
                        edge = self.edges[sub_edge[0]][sub_edge[1]]
                        self.bus_edges.add(edge)
                        
                        if not self.bus_trips[trip_id] or edge != self.bus_trips[trip_id][-1]:
                            if edge in self.bus_trips[trip_id]:
                                edge_id = 0
                                trip_id += 1
                                self.bus_trips[trip_id] = []
                            self.edge_to_trips[edge].add(trip_id)
                            self.bus_trips[trip_id].append(edge)
                            self.edge_pos[trip_id][edge] = edge_id
                            edge_id += 1
                    trip_id += 1
        print(f"There are {len(self.bus_edges)} edges, {trip_id} trips.")

    def count_freq(self, freq, trip, start_index, end_index):
        if start_index + 1 == end_index:
            return
        for edge in trip[start_index + 1:end_index]:
            freq[edge] += 1

    def add_to_edge_matrix(self, edge1, edge2, freq):
        if freq:
            max_value = max(freq.values())
            most_common = [k for k, v in freq.items() if v == max_value]
            self.edge_matrix[edge1][edge2] = most_common

    def save_edge_matrix(self, file_name):
        def convert_tuple_to_strings(d):
            if isinstance(d, dict):
                return {str(k): convert_tuple_to_strings(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [str(edge) if isinstance(edge, tuple) else edge for edge in d]
            else:
                return d
        
        with open(file_name, 'w') as f:
            json.dump(convert_tuple_to_strings(self.edge_matrix), f, indent=4)

    def query_all_pairs_edges(self):
        self.preprocess_graph()
        self.preprocess_bus()
        
        total_combinations = len(self.bus_edges) * (len(self.bus_edges) - 1) // 2

        for edge1, edge2 in tqdm(combinations(self.bus_edges, 2), total=total_combinations, desc="Processing edge matrix"):
            trip_ids = self.edge_to_trips[edge1] & self.edge_to_trips[edge2]
            if not trip_ids:
                continue

            freq_12 = defaultdict(int)
            freq_21 = defaultdict(int)

            for trip_id in trip_ids:
                trip = self.bus_trips[trip_id]
                id1 = self.edge_pos[trip_id][edge1]
                id2 = self.edge_pos[trip_id][edge2]
                if id1 < id2:
                    self.count_freq(freq_12, trip, id1, id2)
                elif id1 > id2:
                    self.count_freq(freq_21, trip, id2, id1)
                else:
                    continue

            self.add_to_edge_matrix(edge1, edge2, freq_12)
            self.add_to_edge_matrix(edge2, edge1, freq_21)
        self.save_edge_matrix("edge_matrix.json")

    def retrieve_edge_matrix(self, edges):
        with open('edge_matrix.json', 'r') as f:
            self.edge_matrix = json.load(f)

        for edge in edges:
            print(f'The row corresponding to {edge} is {self.edge_matrix[str(edge)]}.')

    def get_most_occuring_edge_between(self, edge1, edge2):
        self.preprocess_graph()
        freq = defaultdict(int)
        with open('bus-history.json', 'r', encoding='utf-8') as f:
            for line in f:
                json_object = json.loads(line)
                for path in json_object['tripList']:
                    if not path['edgesOfPath2']:
                        continue
                    trip = []
                    id1 = id2 = None
                    
                    for sub_edge in path['edgesOfPath2']:
                        edge = self.edges[sub_edge[0]][sub_edge[1]]
                        if edge is None:
                            continue
                        
                        if not trip or edge != trip[-1]:
                            if edge in trip:
                                if id1 is not None and id2 is not None:
                                    self.count_freq(freq, trip, id1, id2)
                                id1 = id2 = None
                                trip = []

                            if edge == edge1 and id1 is None:
                                id1 = len(trip)
                            elif edge == edge2 and id1 is not None and id2 is None:
                                id2 = len(trip)
                            
                            trip.append(edge)
                    
                    if id1 is not None and id2 is not None:
                        self.count_freq(freq, trip, id1, id2)

        most_occuring_edge = []
        if freq:
            max_value = max(freq.values())
            most_occuring_edge = [k for k, v in freq.items() if v == max_value]
        print(f"Edges occuring the most between {edge1} and {edge2} are {most_occuring_edge}.")

    def get_most_occuring_edge_between_file(self, edge1, edge2):
        with open('edge_matrix.json', 'r') as f:
            self.edge_matrix = json.load(f)

        print(f"Edges occuring the most between {edge1} and {edge2} are {self.edge_matrix[str(edge1)][str(edge2)]}.")