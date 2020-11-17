#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "Qingqing Cao, https://awk.ai/, Twitter@sysnlp"

from dataclasses import dataclass
from typing import List

from transformers import AutoConfig


@dataclass
class OpNode:
    # op: str
    id: str  # use output node debugName
    scope: str  # scope + id
    op: str  # operation type: matmul, add, mul, div, etc.
    inputs: List[DataNode]
    outputs: List[DataNode]
    # attr: dict[str, Any] = field(default_factory=dict)  # extra information
    flops: int = 0  # number of operations
    mem_bytes: int = 0  # bytes of mem reads and writes


@dataclass
class DataNode:
    id: str
    dtype: str
    shape: List[int]  # tensor shape
    # params: bool = False  # flattened array weights
    # attr: dict[str, Any] = field(default_factory=dict)  # extra information
    # mem_read_bytes: int = 0  # amount of data read from input nodes
    # mem_write_bytes: int = 0  # amount of data written to output nodes


@dataclass
class Module:
    id: str  # scope + id
    nodes: List[OpNode]


@dataclass
class Graph:
    name: str
    nodes: List[OpNode]
    inputs: List[DataNode]
    outputs: List[DataNode]
    # attr: dict[str, Any] = field(default_factory=dict)  # extra information


def construct_graph(trace_graph, name):
    # fc_input_nodes = {i.debugName(): i for i in trace_graph.inputs()}
    # fc_output_nodes = {i.debugName(): i for i in trace_graph.outputs()}
    data_nodes = dict()
    nodes = []
    gi_nodes = []
    go_nodes = []
    ops = set()
    for i, io_node in enumerate(trace_graph.inputs()):
        name = io_node.debugName()
        node_type = io_node.type()
        if isinstance(io_node.type(), torch.TensorType):
            dtype = io_node.type().scalarType()  # Float
            shape = io_node.type().sizes()  # list of int
            ni_node = DataNode(name, dtype, shape)
        else:
            ni_node = DataNode(name, node_type, [])
        gi_nodes.append(ni_node)
        data_nodes[name] = ni_node

    for n in trace_graph.nodes():
        node_inputs = list(n.inputs())
        node_outputs = list(n.outputs())
        node_id = node_outputs[0].debugName()
        node_scope = n.scopeName().replace('__module.', '').split('/')[-1]
        node_op = n.kind()
        ops.add(node_op)
        in_nodes = []
        for ni in node_inputs:
            name = ni.debugName()
            node_type = ni.type()
            if isinstance(node_type, torch.TensorType):
                dtype = ni.type().scalarType()  # Float
                shape = ni.type().sizes()  # list of int
                # TODO: check how to detect if this is a parameter data node
            else:
                # need to handle int, int[], Long(), Device, bool, None
                dtype = node_type
                shape = []
            ni_node = data_nodes.get(name, DataNode(name, dtype, shape))
            in_nodes.append(ni_node)
            data_nodes[name] = ni_node
        out_nodes = []
        for node_out in node_outputs:
            name = node_out.debugName()
            node_type = node_out.type()
            if isinstance(node_type, torch.TensorType):
                dtype = node_out.type().scalarType()  # Float
                shape = node_out.type().sizes()  # list of int
            else:
                # need to handle int, int[], Long(), Device, bool, None
                dtype = node_type
                shape = []
            out_node = data_nodes.get(name, DataNode(name, dtype, shape))
            out_nodes.append(out_node)
            data_nodes[name] = out_node
        op_node = OpNode(node_id, node_scope, node_op, in_nodes, out_nodes)
        nodes.append(op_node)
    graph = Graph(name, nodes, gi_nodes, go_nodes)
    return graph, ops


def resize_graph(dot, size_per_element=0.15, min_size=12):
    """Resize the graph according to how much content it contains.
    Modify the graph in place.
    """
    # Get the approximate number of nodes and edges
    num_rows = len(dot.body)
    content_size = num_rows * size_per_element
    size = max(min_size, content_size)
    size_str = str(size) + "," + str(size)
    dot.graph_attr.update(size=size_str)


if __name__ == '__main__':
    import torch
    from transformers import BertModel

    # from transformers.modeling_bert import BertIntermediate
    model_name = "prajjwal1/bert-tiny"
    config = AutoConfig.from_pretrained(model_name)
    config.hidden_act = 'gelu_fast'
    config.torchscript = True
    model = BertModel(config)
    inputs = torch.randint(1000, size=(1, 100)).long()
    trace = torch.jit.trace(model, inputs)
    # torch.jit.save(trace, "traced_bert-tiny.pt")

    fc_graph = trace.inlined_graph
    graph, graph_ops = construct_graph(fc_graph, model_name)

    # TODO:
    #  - simplify node edges with no data_nodes
    #  - count op types, op counts for scope, data shape
    #  - count flops and mem
    # print(graph)
    max_o = 0
    sn = 0
    tn = 0
    for i, n in enumerate(graph.nodes, 1):
        max_o = max(max_o, len(n.outputs))
        tn += 1
        if n.scope:
            sn += 1
            print(i, n.scope)
    print({k: k.replace("::", "_") for k in sorted(graph_ops)}, max_o, sn, tn)

    # node_attr = dict(style='filled',
    #                  shape='box',
    #                  align='left',
    #                  fontsize='12',
    #                  ranksep='0.1',
    #                  height='0.2')
    # from graphviz import Digraph
    # dot = Digraph(node_attr=node_attr, graph_attr=dict(size="12,12"))
    # scope_nodes = defaultdict(list)  # scope to nodes map
    # # import pygtrie
    # # scope_trie = pygtrie.StringTrie(separator='.')
    # for node in graph.nodes:
    #     op = node.op
    #     scope = node.scope
    #     if not scope:
    #         # no scope nodes belong to the root graph
    #         dot.node(node.id, label=op)
    #         for inp in node.inputs:
    #             dot.edge(inp.id, node.id)
    #     else:
    #         # if scope_trie.has_key(scope):
    #         #     scope_nodes = scope_trie[scope]
    #         #     scope_nodes.append(node)
    #         #     scope_trie[scope] = scope_nodes
    #         # else:
    #         #     scope_trie[scope] = [node]
    #         # scope_trie[scope]
    #         scope_nodes[scope].append(node)
    # for scope, nodes in scope_nodes.items():
    #     sg = Digraph('cluster_' + scope)
    #     print('build nodes and edges', scope)
    #     for n in nodes:
    #         sg.node(n.id, label=scope + '-' + n.op)
    #         for inp in n.inputs:
    #             sg.edge(inp.id, n.id)
    #     sg.body.append(f'label="{scope}"')
    #     dot.subgraph(sg)
    # resize_graph(dot)
    # dot.render('bert-tiny.gv', view=True)
