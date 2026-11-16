import json, time, urllib.request, urllib.parse
A = ['Álvaro Obregón','Azcapotzalco','Benito Juárez','Coyoacán','Cuajimalpa de Morelos','Cuauhtémoc','Gustavo A. Madero','Iztacalco','Iztapalapa','La Magdalena Contreras','Miguel Hidalgo','Milpa Alta','Tláhuac','Tlalpan','Venustiano Carranza','Xochimilco']
UA = {'User-Agent': 'NuestroNido-Rentas/1.0 (mapa personal de rentas; consulta unica de 16 limites)'}
out = []
for a in A:
    q = urllib.parse.urlencode({'q': a + ', Ciudad de México, México', 'format': 'jsonv2', 'polygon_geojson': 1, 'polygon_threshold': 0.0004, 'limit': 5, 'featureType': 'settlement'})
    r = json.load(urllib.request.urlopen(urllib.request.Request('https://nominatim.openstreetmap.org/search?' + q, headers=UA), timeout=60))
    pick = next((x for x in r if x.get('geojson', {}).get('type') in ('Polygon', 'MultiPolygon') and x.get('addresstype') in ('borough', 'city_district', 'municipality', 'county', 'city', 'suburb', 'state_district')), None) or next((x for x in r if x.get('geojson', {}).get('type') in ('Polygon', 'MultiPolygon')), None)
    print(a, '→', pick and (pick['addresstype'], pick['display_name'][:70], pick['geojson']['type'], len(json.dumps(pick['geojson']))))
    if pick: out.append({'n': a.replace(' de Morelos', '').replace('La Magdalena', 'Magdalena'), 'g': pick['geojson'], 'bb': [float(v) for v in pick['boundingbox']]})
    time.sleep(1.2)
json.dump(out, open('build/alcaldias_crudo.json', 'w'), ensure_ascii=False)
