"""P13.1b: 并查集聚簇 + 均衡分批（簇不跨批）"""
import json, os
from collections import defaultdict

with open(r'd:\BaiduNetdiskDownload\西方文论教材\dedup_pairs.json','r',encoding='utf-8') as fh:
    pairs = json.load(fh)

parent = {}
def find(x):
    parent.setdefault(x,x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
def union(a,b):
    ra,rb = find(a),find(b)
    if ra != rb: parent[ra] = rb

for p in pairs:
    union(p['canon'], p['dup'])

clusters = defaultdict(list)
for p in pairs:
    clusters[find(p['canon'])].append(p)

cluster_list = sorted(clusters.values(), key=lambda c: -len(c))
print(f'簇数: {len(cluster_list)}, 页对总数: {len(pairs)}')
print('Top 簇:')
for c in cluster_list[:8]:
    pages = set()
    for p in c:
        pages.add(p['canon']); pages.add(p['dup'])
    print(f'  {len(c)} pairs: {sorted(pages)}')

# 均衡分批：大簇优先，轮流放入当前总对数最少的批
BATCHES = 4
batch_pairs = [[] for _ in range(BATCHES)]
batch_load = [0]*BATCHES
for c in cluster_list:
    i = batch_load.index(min(batch_load))
    batch_pairs[i].extend(c)
    batch_load[i] += len(c)

for i, bp in enumerate(batch_pairs):
    pages = set()
    for p in bp:
        pages.add(p['canon']); pages.add(p['dup'])
    layers = defaultdict(int)
    for pg in pages: layers[pg.split('/')[0]] += 1
    print(f'\n=== 批 {i+1}: {len(bp)} pairs, {len(pages)} pages, layers={dict(layers)} ===')
    for p in bp:
        print(f"  {p['canon']} | {p['dup']}")

for i, bp in enumerate(batch_pairs):
    with open(rf'd:\BaiduNetdiskDownload\西方文论教材\dedup_batch_{i+1}.json','w',encoding='utf-8') as fh:
        json.dump(bp, fh, ensure_ascii=False, indent=1)
print('\nSaved batches 1-4')
