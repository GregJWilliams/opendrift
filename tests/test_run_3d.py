#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of OpenDrift.
#
# OpenDrift is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2
#
# OpenDrift is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OpenDrift.  If not, see <http://www.gnu.org/licenses/>.
#
# Copyright 2015, Knut-Frode Dagestad, MET Norway

import unittest
from datetime import datetime, timedelta
import netCDF4

from opendrift.readers import reader_basemap_landmask
from opendrift.readers import reader_netCDF_CF_generic
from opendrift.readers import reader_ROMS_native
from opendrift.models.pelagicegg import PelagicEggDrift

try:
    netCDF4.Dataset('http://thredds.met.no/thredds/dodsC/sea/norkyst800m/1h/aggregate_be')
    thredds_support = True
except:
    thredds_support = False


class TestRun(unittest.TestCase):

    def test_reader_boundary(self):
        o = PelagicEggDrift(loglevel=0)
        reader_nordic = reader_ROMS_native.Reader(o.test_data_folder() + '2Feb2016_Nordic_sigma_3d/Nordic-4km_SLEVELS_avg_00_subset2Feb2016.nc')
        reader_arctic = reader_netCDF_CF_generic.Reader(o.test_data_folder() + '2Feb2016_Nordic_sigma_3d/Arctic20_1to5Feb_2016.nc') 
        ######################################################
        # Vertical interpolation is another issue to be fixed:
        reader_nordic.zlevels = reader_arctic.z
        ######################################################
        o.add_reader([reader_nordic, reader_arctic])
        o.fallback_values['land_binary_mask'] = 0
        o.fallback_values['x_wind'] = 10  # Some wind for mixing
        # Seed close to Nordic boundary
        o.seed_elements(lon=14.9, lat=71.1, radius=2000, number=100,
                        time=reader_nordic.start_time, z=0)
        o.set_config('turbulentmixing:timestep', 20)
        o.set_config('turbulentmixing:verticalresolution', 1)
        o.set_config('drift:scheme', 'runge-kutta')
        o.run(steps=5, time_step=3600, time_step_output=3600)
        self.assertEqual(o.num_elements_active(), 100)
        self.assertEqual(o.num_elements_deactivated(), 0)
        self.assertAlmostEqual(o.elements.lat[0], 71.148, 2)
        self.assertAlmostEqual(o.elements.z.min(), -35.0, 3)
        self.assertAlmostEqual(o.elements.z.max(), -0.5, 3)
        self.assertAlmostEqual(o.elements.lon.max(), 14.871, 2)

    @unittest.skipIf(thredds_support is False,
                     'NetCDF4 library does not support OPeNDAP')
    def atest_reader_boundary_thredds(self):
        o = PelagicEggDrift(loglevel=0)

        reader_norkyst = reader_netCDF_CF_generic.Reader('http://thredds.met.no/thredds/dodsC/sea/norkyst800m/1h/aggregate_be')
        reader_nordic = reader_netCDF_CF_generic.Reader('http://thredds.met.no/thredds/dodsC/fou-hi/nordic4km-1h/Nordic-4km_SURF_1h_avg_00.nc')
        o.add_reader([reader_norkyst, reader_nordic])
        o.fallback_values['land_binary_mask'] = 0
        lon = 0.2; lat = 61.0; # Close to NorKyst boundary
        time = reader_nordic.start_time
        o.seed_elements(lon, lat, radius=5000, number=100, time=time, z=0)
        o.set_config('turbulentmixing:timestep', 5)
        o.run(steps=5, time_step=3600,
              time_step_output=3600)


if __name__ == '__main__':
    unittest.main()
