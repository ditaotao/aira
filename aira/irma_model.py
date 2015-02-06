import os
import glob
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from osgeo import gdal, ogr, osr
from pthelma.spatial import (extract_point_from_raster,
                             extract_point_timeseries_from_rasters)
from pthelma.swb import SoilWaterBalance

from aira.models import Agrifield

# GEO_DATA_CONFIG_HISTORICAL
PRECIP_FILES_HISTO = glob.glob(os.path.join(settings.AIRA_DATA_HISTORICAL,
                                            'daily_rain*.tif'))

EVAP_FILES_HISTO = glob.glob(os.path.join(settings.AIRA_DATA_HISTORICAL,
                                          'daily_evaporation*.tif'))

# GEO_DATA_CONFIG_FORECAST
PRECIP_FILES_FORE = glob.glob(os.path.join(settings.AIRA_DATA_FORECAST,
                                           'rain*.tif'))

EVAP_FILES_FORE = glob.glob(os.path.join(settings.AIRA_DATA_FORECAST,
                                         'evaporation*.tif'))

FC_FILE = os.path.join(settings.AIRA_COEFFS_RASTERS_DIR,
                       'fc.tif')
PWP_FILE = os.path.join(settings.AIRA_COEFFS_RASTERS_DIR,
                        'pwp.tif')


def rasters2point(lat, long, files):
    # Convert into a pthelma.timeseries
    # a collections of rasters given a point
    point = ogr.Geometry(ogr.wkbPoint)
    sr = osr.SpatialReference()
    sr.ImportFromEPSG(4326)
    point.AssignSpatialReference(sr)
    point.AddPoint(long, lat)
    return extract_point_timeseries_from_rasters(files, point)


def raster2point(lat, long, file):
    # Extract single point information
    # from a given raster
    point = ogr.Geometry(ogr.wkbPoint)
    sr = osr.SpatialReference()
    sr.ImportFromEPSG(4326)
    point.AssignSpatialReference(sr)
    point.AddPoint(long, lat)
    f = gdal.Open(file)
    return extract_point_from_raster(point, f)


def make_tz_datetime(date):
    # Convert datetime.date object to datetime
    # Also make sure datetime object has
    # settings.base.USE_TZ  default as tzinfo
    tz_config = timezone.get_default_timezone()
    return datetime(date.year, date.month, date.day).replace(tzinfo=tz_config)


def data_finish_date(precipitation, evapotranspiration):
    # Searching for AIRA_DATA_FILE_DIR to find
    # the common time period with the latest record
    # in precipitation and evaporation rasters.
    plast = precipitation.bounding_dates()[1]
    elast = evapotranspiration.bounding_dates()[1]
    return min(plast, elast)


def data_start_date(precipitation, evapotranspiration):
    # Searching for AIRA_DATA_FILE_DIR to find
    # the common time start date for data availiabiliy
    plast = precipitation.bounding_dates()[0]
    elast = evapotranspiration.bounding_dates()[0]
    return max(plast, elast)


def location_warning(agrifield_id, precip_files, evap_files):
    # Simplified check if agrifield location is inside dataset rasters
    # Need to add some more sophisticated using dgal.
    # In order not to break model calculations
    # and home view we use Arta city location as default.
    f = Agrifield.objects.get(pk=agrifield_id)
    try:
        location_warning = False
        precip = rasters2point(f.latitude, f.longitude, precip_files)
        evap = rasters2point(f.latitude, f.longitude, evap_files)
        return precip, evap, location_warning
    except:
        location_warning = True
        precip = rasters2point(39.15, 20.98, PRECIP_FILES_HISTO)
        evap = rasters2point(39.15, 20.98, EVAP_FILES_HISTO)
        return precip, evap, location_warning


def timeperiod_warning(agrifield_id, precip, evap):
    # Warning about 2 cases
    # 1. User haven't added irrigation log
    # 2. User latest irrigation log isnt in dataset raster timeperiod
    # In both cases advice is estimated based of available timeperiod datasets
    warning = None
    f = Agrifield.objects.get(pk=agrifield_id)
    start_date = make_tz_datetime(data_start_date(precip, evap))
    if not f.irrigationlog_set.exists():
        warning = True
        return start_date, warning
    latest_irrigation = f.irrigationlog_set.latest().time
    latest_irrigation = make_tz_datetime(latest_irrigation)
    if latest_irrigation < start_date:
        warning = True
        return start_date, warning
    return latest_irrigation, warning


def irrigation_amount_view(agrifield_id):
    try:
        # Panta exei giati einia f for in
        # Select Agrifield
        f = Agrifield.objects.get(pk=agrifield_id)
        # Create Timeseries given Agrifield location
        precip, evap, warning_loc = location_warning(agrifield_id,
                                                     PRECIP_FILES_HISTO,
                                                     EVAP_FILES_HISTO)
        # Extract pthelma.swb parameter information
        fc = raster2point(f.latitude, f.longitude, FC_FILE)
        wp = raster2point(f.latitude, f.longitude, PWP_FILE)
        rd = (float(f.ct.ct_rd_min) + float(f.ct.ct_rd_max)) / 2
        kc = float(f.ct.ct_kc)
        irr_eff = float(f.irrt.irrt_eff)
        start_date, warning_dates = timeperiod_warning(agrifield_id,
                                                       precip, evap)
        # Validation about initial conditions
        init_sm = FC_FILE
        if warning_dates is True:
            init_sm = 0
        p = float(f.ct.ct_coeff)
        rd_factor = 1
        finish_date = make_tz_datetime(data_finish_date(precip, evap))
        # Apply pthelma.swb model
        s = SoilWaterBalance(fc, wp, rd, kc, p,
                             precip, evap,
                             irr_eff, rd_factor)
        # From aira_warings start and finish date
        next_irr = s.irrigation_water_amount(start_date, init_sm, finish_date)
        next = dict(s=s, next_irr=str(round(next_irr, 2)),
                    warning_loc=warning_loc, warning_dates=warning_dates,
                    start_date=start_date, fc=fc)
    except:
        next = dict(s=None, next_irr=None, warning_loc=None,
                    warning_dates=None, start_date=None, fc=None)
    return next
