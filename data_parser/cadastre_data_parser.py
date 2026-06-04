

import geopandas as gpd
import pandas as pd
import argparse
import os

data_prefix = "data"
geojson_prefix = "geojson"
geojson_suffix = ".geojson"
buildings_filename = "buildings"

def merge_geojsons(geojson_paths, args):
    
    if len(geojson_paths) == 1:
        os.rename(geojson_paths[0], args.output_geojson)
        return

    gpds = []
    for geojson_path in geojson_paths:
        gpds.append(gpd.read_file(geojson_path))
    
    print(f"Merging GeoJSONs")
    merged = gpd.GeoDataFrame(pd.concat(gpds, ignore_index=True), crs=gpds[0].crs)

    print(f"Saving GeoJSON to: {args.output_geojson}")
    merged.to_file(args.output_geojson, driver="GeoJSON")

def parse_shapefiles(args):

    geojson_paths = []
    
    for shp_path in args.shp_paths.split(","):

        gdf = gpd.read_file(shp_path)
        
        if args.filter:
            gdf = gdf[gdf['functype'].str.contains(args.filter, case=False, regex=True, na=False)]
        
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
    parser.add_argument('--shp_paths', dest='shp_paths', help='Path to shapefiles. Should be comma-separated files if you want to specify multiple of them.')
    parser.add_argument('--filter', dest='filter', help='Filter which buildings should be included in the GeoJSON.')
    parser.add_argument('--output_geojson', dest='output_geojson', help='Specify where to save the GeoJSON file.', default=f"{data_prefix}/{geojson_prefix}/{buildings_filename}{geojson_suffix}")

    args = parser.parse_args()

    geojsons = parse_shapefiles(args)
    merge_geojsons(geojsons, args)

if __name__ == '__main__':
    main()