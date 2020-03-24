###############################################################################
#   0. Imports                                                                #
###############################################################################
# Import Operation System (os) package
import os
import arcpy

###############################################################################
#   1. Setup                                                                  #
###############################################################################
# Specify the parent folder as the working directory of the operating system
os.chdir(arcpy.GetParameterAsText(0))
keep_gdb = arcpy.GetParameterAsText(1)


###############################################################################
#   2. Specifications (update for VP3 in primo 2022)                          #
###############################################################################
# Specify the names of each type of water body and its data files
data = {'streams':['streams_DVFI_1992-2018.xlsx','streams_DVFI_2019-.xlsx']}

# Specify the names of the corresponding linkage files
linkage = {'streams':'streams_stations_VP2.xlsx'}

# WFS service for the current water body plan (VP2 is for 2015-2021)
wfs_service = 'http://wfs2-miljoegis.mim.dk/vp2_2016/ows?version=1.1.0&request=GetCapabilities&service=wfs'

# Specify the names of the feature class (fc) for each type of water body
wfs_fc = {'streams':'vp2bek_2019_vandlob'}

# Specify the field (column) names in the fc that contain the water body ID
wfs_vpID = {'streams':'g_del_cd'}

# Specify the field (column) names in the fc that contain the water body size
wfs_size = {'streams':'g_len'}


###############################################################################
#   3. Import module and run the functions                                    #
###############################################################################
# Import the module with all the homemade functions
import script_module

# Initialize the class for all data processing and mapping functions
c = script_module.Water_Quality(data, linkage, wfs_fc, wfs_vpID, wfs_size, keep_gdb)

# Check that the folders with data and linkage files exist or create them
c.get_data()

# Loop over each type of water body (to be extended with lakes and coastal waters)
for waterbodyType in data:

    # Get the feature class from the WFS service
    c.get_fc_from_WFS(waterbodyType, wfs_service)

    # Create a Pandas DataFrame with ecological status by year
    df, years = c.ecological_status(waterbodyType)

    # Create a map book with yearly maps of ecological status
    c.map_book(waterbodyType, df, years)

