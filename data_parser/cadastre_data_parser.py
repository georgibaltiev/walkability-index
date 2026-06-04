

import geopandas as gpd
import pandas as pd
import argparse
import os

data_prefix = "data"
geojson_prefix = "geojson"
geojson_suffix = ".geojson"
buildings_filename = "buildings"

def merge_geojsons(geojson_paths, output_path):
    
    if len(geojson_paths) == 1:
        os.rename(geojson_paths[0], output_path)
        return

    gpds = []
    for geojson_path in geojson_paths:
        gpds.append(gpd.read_file(geojson_path))
    
    print(f"Merging GeoJSONs")
    merged = gpd.GeoDataFrame(pd.concat(gpds, ignore_index=True), crs=gpds[0].crs)

    print(f"Saving GeoJSON to: {output_path}")
    merged.to_file(output_path, driver="GeoJSON")

def parse_shapefiles(args):

    geojson_paths = []
    
    for shp_path in args.shp_paths.split(","):
        
        gdf = gpd.read_file(shp_path)
        shp_name = os.path.basename(shp_path).split(".")[0]
        
        gdf = gdf.to_crs(epsg=4326)

        if not os.path.exists(f"{data_prefix}/{geojson_prefix}"):
            print(f"Creating GeoJSON directory: {data_prefix}/{geojson_prefix}")
            os.makedirs(f"{data_prefix}/{geojson_prefix}")
        
        output_path = f"{data_prefix}/{geojson_prefix}/{shp_name}{geojson_suffix}"
        
        print(f"Saving GeoJSON to: {output_path}")
        
        gdf.to_file(output_path, driver='GeoJSON', index=False)
        geojson_paths.append(output_path)
    
    return geojson_paths

def main():

    parser = argparse.ArgumentParser(description='Parse parameters for the shp converter')
    parser.add_argument('--shp_paths', help='Path to shapefiles. Should be comma-separated files if you want to specify multiple of them.')
    # parser.add_argument('--limit', type=int, default=None, help='Limit number of features (useful for testing)')
    parser.add_argument('--filter', dest='filter_type', default=None, help='Filter which buildings should be examined"')
    
    args = parser.parse_args()

    geojsons = parse_shapefiles(args)
    merge_geojsons(geojsons, f"{data_prefix}/{geojson_prefix}/{buildings_filename}{geojson_suffix}")

if __name__ == '__main__':
    main()