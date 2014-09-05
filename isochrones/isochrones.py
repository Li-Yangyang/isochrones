from __future__ import division,print_function

__author__ = 'Timothy D. Morton <tim.morton@gmail.com>'
"""


"""

import numpy as np
import os,sys,re,os.path

from scipy.interpolate import LinearNDInterpolator as interpnd
import scipy.optimize
import numpy.random as rand
import emcee

from astropy import constants as const

import matplotlib.pyplot as plt
from plotutils.plotutils import setfig

#Define useful constants
G = const.G.cgs.value
MSUN = const.M_sun.cgs.value
RSUN = const.R_sun.cgs.value

DATADIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))

#Read data defining extinction in different bands (relative to A_V)
EXTINCTIONFILE = '{}/extinction.txt'.format(DATADIR)
EXTINCTION = dict()
EXTINCTION5 = dict()
for line in open(EXTINCTIONFILE,'r'):
    line = line.split()
    EXTINCTION[line[0]] = float(line[1])
    EXTINCTION5[line[0]] = float(line[2])

EXTINCTION['kep'] = 0.85946
EXTINCTION['V'] = 1.0
EXTINCTION['Ks'] = EXTINCTION['K']
EXTINCTION['Kepler'] = EXTINCTION['kep']



class Isochrone(object):
    """Generic isochrone class. Everything is function of mass, logage, feh.

    Can be instantiated directly, but will typically be used with a pre-defined
    subclass.  

    The following methods are implemented as 3-d interpolation functions, all
    taking as arguments (mass,age,feh):

    M, logL, logg, logTeff, Teff, R

    Also defined is a dictionary property 'mag' where self.mag[band] is also
    a similarly-constructed interpolation function.
    
    Parameters
    ----------
    m_ini : array-like
        Initial mass [msun]

    age : array-like
        log_10(age) [yr]

    feh : array-like
        Metallicity

    m_act : array-like
        Actual mass; same as m_ini if mass loss not implemented [msun]

    logL : array-like
        log_10(luminosity) [solar units]

    Teff : array-like
        Effective temperature [K]

    logg : array-like
        log_10(surface gravity) [cgs]

    mags : dict
        dictionary of magnitudes in different bands

    tri : `scipy.spatial.qhull.Delaunay` object, optional
        This is used to initialize the interpolation functions.
        If pre-computed triangulation not provided, then the constructor
        will calculate one.  This might take several minutes, so be patient.
        Much better to use pre-computed ones.
        
    """
    def __init__(self,m_ini,age,feh,m_act,logL,Teff,logg,mags,tri=None):
        """Warning: if tri object not provided, this will be very slow to be created.
        """

        self.minage = age.min()
        self.maxage = age.max()
        self.minmass = m_act.min()
        self.maxmass = m_act.max()
        self.minfeh = feh.min()
        self.maxfeh = feh.max()
        

        L = 10**logL

        if tri is None:
            points = np.zeros((len(m_ini),2))
            points[:,0] = m_ini
            points[:,1] = age
            self.mass = interpnd(points,m_act)
            self.tri = self.mass.tri
        else:
            self.tri = tri
            self.mass = interpnd(self.tri,m_act)

        self.logL = interpnd(self.tri,logL)
        self.logg = interpnd(self.tri,logg)
        self.logTeff = interpnd(self.tri,np.log10(Teff))

        def Teff_fn(*pts):
            return 10**self.logTeff(*pts)
        self.Teff = Teff_fn
        
        def R_fn(*pts):
            return np.sqrt(G*self.mass(*pts)*MSUN/10**self.logg(*pts))/RSUN
        self.radius = R_fn

        self.bands = []
        for band in mags.keys():
            self.bands.append(band)

        self.mag = {band:interpnd(self.tri,mags[band]) for band in self.bands}       
        
    def __call__(self,*args):
        """returns properties (or arrays of properties) at given mass, age, feh

        Parameters
        ----------
        mass, age, feh : float or array-like

        Returns
        -------
        values : dictionary
            Dictionary of floats or arrays, containing 'age', 'mass',
            'radius', 'logL', 'logg', 'Teff', 'mag', where 'mag' is itself
            a dictionary of magnitudes. 
        """
        m,age,feh = args 
        Ms = self.mass(*args)
        Rs = self.radius(*args)
        logLs = self.logL(*args)
        loggs = self.logg(*args)
        Teffs = self.Teff(*args)
        mags = {band:self.mag[band](*args) for band in self.bands}
        
        return {'age':age,'mass':Ms,'radius':Rs,'logL':logLs,
                'logg':loggs,'Teff':Teffs,'mag':mags}        


    def evtrack(self,m,feh=0.0,minage=None,maxage=None,dage=0.02):
        """Returns evolution track for a single initial mass and feh

        Parameters
        ----------
        m : float
            initial mass of desired track

        feh : float, optional
            metallicity of desired track.  Default = 0.0 (solar)

        minage, maxage : float, optional
            Minimum and maximum log(age) of desired track. Will default
            to min and max age of model isochrones. 

        dage : float, optional
            Spacing in log(age) at which to evaluate models.  Default = 0.02

        Returns
        -------
        values : dictionary
            Dictionary of arrays representing evolution track, containing 'age',
            'mass', 'radius', 'logL', 'logg', 'Teff', 'mag', where 'mag' is itself
            a dictionary of magnitudes.
        """
        if minage is None:
            minage = self.minage
        if maxage is None:
            maxage = self.maxage
        ages = np.arange(minage,maxage,dage)
        Ms = self.mass(m,ages,feh)
        Rs = self.radius(m,ages,feh)
        logLs = self.logL(m,ages,feh)
        loggs = self.logg(m,ages,feh)
        Teffs = self.Teff(m,ages,feh)
        mags = {band:self.mag[band](m,ages,feh) for band in self.bands}

        return {'age':ages,'mass':Ms,'radius':Rs,'logL':logLs,
                'logg':loggs, 'Teff':Teffs, 'mag':mags}
            
    def isochrone(self,age,feh=0.0,minm=None,maxm=None,dm=0.02):
        """Returns stellar models evaluated at a constant age and feh, for a range of masses

        Parameters
        ----------
        age : float
            log(age) of desired isochrone.

        feh : float
            Metallicity of desired isochrone (default = 0.0)

        minm, maxm : float
            Mass range of desired isochrone (will default to max and min available)

        dm : float
            Spacing in mass of desired isochrone

        Returns
        -------
        values : dictionary
            Dictionary of arrays representing evolution track, containing
            'M', 'R', 'logL', 'logg', 'Teff', 'mag', where 'mag' is itself
            a dictionary of magnitudes.

        """
        if minm is None:
            minm = self.minmass
        if maxm is None:
            maxm = self.maxmass
        ms = np.arange(minm,maxm,dm)
        ages = np.ones(ms.shape)*age

        Ms = self.mass(ms,ages,feh)
        Rs = self.radius(ms,ages,feh)
        logLs = self.logL(ms,ages,feh)
        loggs = self.logg(ms,ages,feh)
        Teffs = self.Teff(ms,ages,feh)
        mags = {band:self.mag[band](ms,ages,feh) for band in self.bands}
        #for band in self.bands:
        #    mags[band] = self.mag[band](ms,ages)

        return {'M':Ms,'R':Rs,'logL':logLs,'logg':loggs,
                'Teff':Teffs,'mag':mags}        
        


