import os
import cv2 as cv
import numpy as np



class KalmanFilter2D:
    def __init__(self,npoints,dt):
        self.npoints = npoints
        self.dt = dt

        nstates = self.npoints*4
        nmeasures = self.npoints*2
        self.kf = cv.KalmanFilter(nstates,nmeasures)
        self.kf.transitionMatrix = np.eye(nstates,dtype=np.float32)
        self.kf.measurementNoiseCov = np.eye(nmeasures,dtype=np.float32)*0.0005
        
        for i in range(nmeasures):
            self.kf.transitionMatrix[i][i+nmeasures] = dt
        
        measurementMatrix = np.zeros([nmeasures,nstates],dtype=np.float32)
        for i in range(nmeasures):
            measurementMatrix[i][i] = 1.0
        self.kf.measurementMatrix = measurementMatrix

    def update_dt(self,dt):
        nmeasures = self.npoints*2
        for i in range(nmeasures):
            self.kf.transitionMatrix[i][i+nmeasures] = dt
            
    def predict(self,points):
        points = np.float32(np.ndarray.flatten(points))
        self.kf.correct(points)
        tp = self.kf.predict()
        return tp.T[:,:self.npoints*2]
