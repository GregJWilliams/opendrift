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

import os
import numpy as np
from datetime import datetime
import logging

from opendrift.models.openoil import OpenOil, Oil
from opendrift.models.opendrift3D import OpenDrift3DSimulation


# Defining the oil element properties
class Oil3D(Oil):
    """Extending Oil class with variables relevant for the vertical."""

    variables = Oil.add_variables([
        # Entrainment length scale, see Tkalich and Chan (2002)
        ('entrainment_length_scale', {'dtype': np.float32,
                                      'units': 'm',
                                      'default': 0.1}),
        ('diameter', {'dtype': np.float32,  # Particle diameter
                      'units': 'm',
                      'default': 1e-5})
        ])


class OpenOil3D(OpenDrift3DSimulation, OpenOil):  # Multiple inheritance
    """Open source oil trajectory model based on the OpenDrift framework.

        Developed at MET Norway based on oil weathering parameterisations
        found in open/published litterature.

        Under construction.
    """

    ElementType = Oil3D

    required_variables = [
        'x_sea_water_velocity', 'y_sea_water_velocity',
        'sea_surface_wave_significant_height',
        'sea_surface_wave_stokes_drift_x_velocity',
        'sea_surface_wave_stokes_drift_y_velocity',
        'sea_surface_wave_period_at_variance_spectral_density_maximum',
        'sea_surface_wave_mean_period_from_variance_spectral_density_second_frequency_moment',
        'sea_ice_area_fraction',
        'x_wind', 'y_wind', 'land_binary_mask',
        'sea_floor_depth_below_sea_level',
        'ocean_vertical_diffusivity',
        'sea_water_temperature',
        'sea_water_salinity',
        'upward_sea_water_velocity'
        ]

    required_profiles = ['sea_water_temperature',
                         'sea_water_salinity',
                         'ocean_vertical_diffusivity']
    # The depth range (in m) which profiles shall cover
    required_profiles_z_range = [-120, 0]

    fallback_values = {
        'x_sea_water_velocity': 0,
        'y_sea_water_velocity': 0,
        'sea_surface_wave_significant_height': 0,
        'sea_surface_wave_stokes_drift_x_velocity': 0,
        'sea_surface_wave_stokes_drift_y_velocity': 0,
        'sea_surface_wave_period_at_variance_spectral_density_maximum': 0,
        'sea_surface_wave_mean_period_from_variance_spectral_density_second_frequency_moment': 0,
        'sea_ice_area_fraction': 0,
        'x_wind': 0, 'y_wind': 0,
        'sea_floor_depth_below_sea_level': 10000,
        'ocean_vertical_diffusivity': 0.02,  # m2s-1
        'sea_water_temperature': 10.,
        'sea_water_salinity': 34.,
        'upward_sea_water_velocity': 0
        }

    max_speed = 1.0  # m/s

    # Read oil types from file (presently only for illustrative effect)
    oil_types = str([str(l.strip()) for l in open(
                    os.path.dirname(os.path.realpath(__file__)) +
                    '/oil_types.txt').readlines()])[1:-1]
    default_oil = oil_types.split(',')[0].strip()

    # Configuration
    configspecOO3D = '''
        [input]
            [[spill]]
                oil_type = option(%s, default=%s)
                droplet_diameter_min_subsea = float(min=1e-8, max=1, default=0.0005)
                droplet_diameter_max_subsea = float(min=1e-8, max=1, default=0.005)
        [turbulentmixing]
            droplet_diameter_min_wavebreaking = float(default=1e-5, min=1e-8, max=1)
            droplet_diameter_max_wavebreaking = float(default=1e-3, min=1e-8, max=1)
            droplet_size_exponent = float(default=0, min=-10, max=10)
    ''' % (oil_types, default_oil)

    def __init__(self, *args, **kwargs):

        # Read oil properties from file
        self.oiltype_file = os.path.dirname(os.path.realpath(__file__)) + \
            '/oilprop.dat'
        oilprop = open(self.oiltype_file)
        oiltypes = []
        linenumbers = []
        for i, line in enumerate(oilprop.readlines()):
            if line[0].isalpha():
                oiltype = line.strip()[:-2].strip()
                oiltypes.append(oiltype)
                linenumbers.append(i)
        oiltypes, linenumbers = zip(*sorted(zip(oiltypes, linenumbers)))
        self.oiltypes = oiltypes
        self.oiltypes_linenumbers = linenumbers

        self._add_configstring(self.configspecOO3D)

        # Calling general constructor of parent class
        super(OpenOil3D, self).__init__(*args, **kwargs)

    def seed_elements(self, *args, **kwargs):

        if 'number' not in kwargs:
            number = 1
        else:
            number = kwargs['number']
        if 'diameter' in kwargs:
            logging.info('Droplet diameter is provided, and will '
                         'be kept constant during simulation')
            self.keep_droplet_diameter = True
        else:
            self.keep_droplet_diameter = False
        if 'z' not in kwargs:
            kwargs['z'] = 0
        if kwargs['z'] == 'seafloor':
            z = -np.ones(number)
        else:
            z = np.atleast_1d(kwargs['z'])
        if len(z) == 1:
            z = z*np.ones(number)  # Convert scalar z to array
        subsea = z < 0
        if np.sum(subsea) > 0 and 'diameter' not in kwargs:
            # Droplet min and max for particles seeded below sea surface
            sub_dmin = self.get_config('input:spill:droplet_diameter_min_subsea')
            sub_dmax = self.get_config('input:spill:droplet_diameter_max_subsea')
            logging.info('Using particle diameters between %s and %s m for '
                         'elements seeded below sea surface.' %
                         (sub_dmin, sub_dmax))
            kwargs['diameter'] = np.random.uniform(sub_dmin, sub_dmax, number)

        super(OpenOil3D, self).seed_elements(*args, **kwargs)

    def particle_radius(self):
        """Calculate radius of entained particles.

        Per now a fixed radius, should later use a distribution.
        """

        # Delvigne and Sweeney (1988)
        # rmax = 1818*np.power(self.wave_energy_dissipation(), -0.5)* \
        #             np.power(self.elements.viscosity, 0.34) / 1000000

        # r = np.random.uniform(0, rmax, self.num_elements_active())
        return self.elements.diameter/2  # Hardcoded diameter

    def update_terminal_velocity(self, Tprofiles=None,
                                 Sprofiles=None, z_index=None):
        """Calculate terminal velocity for oil droplets

        according to
        Tkalich et al. (2002): Vertical mixing of oil droplets
                               by breaking waves
        Marine Pollution Bulletin 44, 1219-1229

        If profiles of temperature and salt are passed into this function,
        they will be interpolated from the profiles.
        if not, T,S will be fetched from reader.
        """
        g = 9.81  # ms-2

        r = self.particle_radius()*2

        # prepare interpolation of temp, salt

        if not (Tprofiles is None and Sprofiles is None):
            if z_index is None:
                z_i = range(Tprofiles.shape[0])  # evtl. move out of loop
                # evtl. move out of loop
                z_index = interp1d(-self.environment_profiles['z'],
                                   z_i, bounds_error=False)
            zi = z_index(-self.elements.z)
            upper = np.maximum(np.floor(zi).astype(np.int), 0)
            lower = np.minimum(upper+1, Tprofiles.shape[0]-1)
            weight_upper = 1 - (zi - upper)

        # do interpolation of temp, salt if profiles were passed into
        # this function, if not, use reader by calling self.environment
        if Tprofiles is None:
            T0 = self.environment.sea_water_temperature
        else:
            T0 = Tprofiles[upper, range(Tprofiles.shape[1])] * \
                weight_upper + \
                Tprofiles[lower, range(Tprofiles.shape[1])] * \
                (1-weight_upper)
        if Sprofiles is None:
            S0 = self.environment.sea_water_salinity
        else:
            S0 = Sprofiles[upper, range(Sprofiles.shape[1])] * \
                weight_upper + \
                Sprofiles[lower, range(Sprofiles.shape[1])] * \
                (1-weight_upper)

        rho_oil = self.elements.density
        rho_water = self.sea_water_density(T=T0, S=S0)

        # dynamic water viscosity
        my_w = 0.001*(1.7915 - 0.0538*T0 + 0.007*(T0**(2.0)) - 0.0023*S0)
        # ~0.0014 kg m-1 s-1
        # kinemativ water viscosity
        ny_w = my_w / rho_water
        rhopr = rho_oil/rho_water

        # terminal velocity for low Reynolds numbers
        kw = 2*g*(1-rhopr)/(9*ny_w)
        W = kw * r**2

        # check if we are in a high Reynolds number regime
        Re = 2*r*W/ny_w
        highRe = np.where(Re > 50)

        # Terminal velocity in high Reynolds numbers
        kw = (16*g*(1-rhopr)/3)**0.5
        W2 = kw*r**0.5

        W[highRe] = W2[highRe]
        self.elements.terminal_velocity = W

    def oil_wave_entrainment_rate(self):
        kb = 0.4
        omega = (2.*np.pi)/self.wave_period()
        gamma = self.wave_damping_coefficient()
        alpha = 1.5
        Low = self.elements.entrainment_length_scale
        entrainment_rate = \
            kb*omega*gamma*self.significant_wave_height() / \
            (16*alpha*Low)
        return entrainment_rate

    def prepare_vertical_mixing(self):
        '''Calculate entrainment probability before main loop'''
        self.oil_entrainment_probability = \
            self.oil_wave_entrainment_rate()*\
                self.get_config('turbulentmixing:timestep')
        # Calculate a random droplet diameter for each particle,
        # to be used if this particle gets entrained
        self.droplet_diamenter_if_entrained = \
            self.get_wave_breaking_droplet_diameter(self.num_elements_active())
        # Uncomment lines below to plot droplet size distribution at each step
        #import matplotlib.pyplot as plt
        #plt.hist(self.droplet_diamenter_if_entrained, 200)
        #plt.gca().set_xscale("log")
        #plt.gca().set_yscale("log")
        #plt.show()

    def surface_interaction(self, time_step_seconds, alpha=1.5):
        """Mix surface oil into water column."""

        # Place particles above surface to exactly 0
        surface = self.elements.z >= 0
        self.elements.z[surface] = 0

        # Entrain oil into uppermost layer (whitecapping from waves)
        # TODO: optimise this by only calculate for surface elements
        random_number = np.random.uniform(0, 1, len(self.elements.z))
        entrained = np.logical_and(surface,
                        random_number<self.oil_entrainment_probability)
        self.elements.z[entrained] = \
            -self.get_config('turbulentmixing:verticalresolution')/2.
        if self.keep_droplet_diameter is False:
            # Give newly entrained droplets a random diameter
            self.elements.diameter[entrained] = \
                self.droplet_diamenter_if_entrained[entrained]

    def get_wave_breaking_droplet_diameter(self, number):
        if not hasattr(self, 'droplet_spectrum_pdf'):
            # Generate droplet spectrum, if not already done
            logging.info('Generating wave breaking droplet size spectrum')
            s = self.get_config('turbulentmixing:droplet_size_exponent')
            dmax = self.get_config('turbulentmixing:droplet_diameter_max_wavebreaking')
            dmin = self.get_config('turbulentmixing:droplet_diameter_min_wavebreaking')
            # Note: a long array of diameters is required for 
            # sufficient resolution at both ends of logarithmic scale.
            # Could perhaps use logspace instead of linspace(?)
            self.droplet_spectrum_diameter = np.linspace(dmin, dmax, 1000000)
            spectrum = self.droplet_spectrum_diameter**s
            self.droplet_spectrum_pdf = spectrum/np.sum(spectrum)

        return np.random.choice(self.droplet_spectrum_diameter, size=number,
                                p=self.droplet_spectrum_pdf)

    def resurface_elements(self, minimum_depth=None):
        """Oil elements reaching surface (or above) form slick, not droplet"""
        surface = np.where(self.elements.z >= 0)[0]
        self.elements.z[surface] = 0

    def update(self):
        """Update positions and properties of oil particles."""

        # Oil weathering (inherited from OpenOil)
        self.oil_weathering()

        # Turbulent Mixing
        if self.get_config('processes:turbulentmixing') is True:
            self.update_terminal_velocity()
            self.vertical_mixing()

        # Vertical advection
        if self.get_config('processes:verticaladvection') is True:
            self.vertical_advection()

        # Horizontal advection (inherited from OpenOil)
        self.advect_oil()
