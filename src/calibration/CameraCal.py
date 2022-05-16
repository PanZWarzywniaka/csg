
from .CamCal_config import Config
from .CamParam import CamParam
import math
from  .cameracalib import I2WCal
from .ParamRng import ParamRng
import numpy as np
from tkinter import *
from tkinter import  ttk
#import skimage.io


def rotPt(coor,th):
    cx = 0
    cy = 0  # centre of square coords
    x=coor[0]-cx
    y=coor[1]-cy
    new_x = x * math.cos(th) - y * math.sin(th)
    new_y = x * math.sin(th) + y * math.cos(th)
    x = new_x + cx
    y = new_y + cy
    return [x, y]


class CamCal:

    def __init__(self):
        self.CamParam=CamParam()
        self.init_VP_r = [self.CamParam.img_width-1,0]
        self.init_VP_l =[0,0]
        self.init_PP=[self.CamParam.img_width/2,self.CamParam.img_height/2]
        self.voCamParam = []
        self.seedParam=[]
        self.sParamRng=ParamRng()

#calibrates camera by direct computation
    def process(self, voVanPt,SegNdPt,SegDist):
        self.MeasLnSegNdPt = SegNdPt
        self.MeasLnSegDist = SegDist
        if len(voVanPt)== 2:
            self.init_VP_r = voVanPt[0]
            self.init_VP_l = voVanPt[1]
            #estPrinPtByAC()
        # w / o optimization
        if not Config.CalEdaOptFlg:
            self.calCamDctComp()
        else:
            self.calCamEdaOpt()

    def calCamDctComp(self):
        #fReprojErr=0
        fCamHei = (Config.CalCamHeiMax + Config.CalCamHeiMin) / 2
        self.compCamParam(self.init_VP_r, self.init_VP_l, self.init_PP, fCamHei)
        #oStGrdPt = calcStGrdPt(self.CamParam)
        fReprojErr = self.calcReprojErr(self.CamParam)
        print("Reprojection error = %.7f\n", fReprojErr)
        #plt3dGrd(&oCamParam, m_oVr, m_oVl, oStGrdPt)

#calibrates camera by EDA optimization
    def calCamEdaOpt(self):
        nR = Config.EDA_INIT_POP
        nN = Config.EDA_SEL_POP
        nIterNum = Config.EDA_ITER_NUM
        iIter = 0
        ## set starting grid point
        fCamHei = (Config.CalCamHeiMax + Config.CalCamHeiMin) / 2
        self.compCamParam(self.init_VP_r, self.init_VP_l, self.init_PP, fCamHei)

        #oStGrdPt = calcStGrdPt(self.CamParam)
        ## initialize range of each parameter
        self.initEdaParamRng(0)
        ## EDA optimization EMNA -global
        if nN >= nR:
            print("Error: Selected population should be less than initial population")
        for iR in range(0,nR):
            temp_Param = CamParam()
            temp_Param.initCamMdl(self.sParamRng)
            self.voCamParam.append(temp_Param)
        print("Start EDA optimization for camera calibration\n")
        popup_msg =Toplevel()#,takefocus=True)
        popup_msg.geometry("%dx%d+%d+%d" % (400,40, 500,400))
        popup_msg.grab_set()
        popup_msg.resizable(False, False)
        progress_var = DoubleVar()
        progress_bar = ttk.Progressbar(popup_msg, variable=progress_var, maximum=100,
                                     orient=HORIZONTAL, length=350)#, mode="indeterminate")
        progress_bar.pack(side=TOP)
        popup_msg.pack_slaves()
        popup_msg.update()

        fReprojErrMeanPrev=0
        while nIterNum > iIter:
           # print("==== generation %d: ====\n", iIter)
            progress_var.set(round(iIter/nIterNum)*100)
            popup_msg.update()
            fReprojErrMean = 0.0
            fReprojErrStd = 0.0
            fReprojErrList=np.zeros((nR,1))
            for idx, ivoCamParam in enumerate(self.voCamParam):
                fFx = ivoCamParam.Fx
                fFy = ivoCamParam.Fy
                fCx = ivoCamParam.Cx
                fCy = ivoCamParam.Cy
                fRoll = ivoCamParam.Roll
                fPitch = ivoCamParam.Pitch
                fYaw = ivoCamParam.Yaw
                fTx = ivoCamParam.Tx
                fTy = ivoCamParam.Ty
                fTz = ivoCamParam.Tz
                oCamParam = CamParam()
                oCamParam.setMatrix_K(fFx, fFy, fCx, fCy)
                oCamParam.setMatrix_R(fRoll, fPitch, fYaw)
                oCamParam.setMatrix_T(fTx, fTy, fTz)
                oCamParam.calMatrix_P()
                P=oCamParam.Mat_P
                fReprojErr = self.calcReprojErr(P)
                ivoCamParam.setReprojErr(fReprojErr)
                fReprojErrList[idx]=fReprojErr

            fReprojErrMean = np.mean(fReprojErrList)
            fReprojErrStd = np.std(fReprojErrList)
            dif = abs(fReprojErrMean - fReprojErrMeanPrev)
            ## Check if generation needs to stop
            if iIter>0 and dif < Config.EDA_REPROJ_ERR_THLD*fReprojErrMeanPrev:
                print("Reprojection error is small enough. Stop generation.\n")
                break
            fReprojErrMeanPrev = fReprojErrMean
            #select error min params to re-estimate paramRNG
            self.voCamParam.sort(key=lambda x:x.fReprojErr,reverse=False)
            self.seedParam=self.voCamParam[0:nN]

            #plt3dGrd( & oCamParam, m_oVr, m_oVl, oStGrdPt)
            self.estEdaParamRng(self.seedParam)
            self.voCamParam=[]
            for iR in range(0,nR):
                temp_Param=CamParam()
                temp_Param.initCamMdl(self.sParamRng)
                self.voCamParam.append(temp_Param)
            iIter += 1

        if nIterNum <= iIter :
            print("Exit: Results can not converge.\n")
        popup_msg.destroy()

#computes camera parameters, set mat P/K/R/T
    def compCamParam(self, oVr, oVl, oPrinPt, fCamHei):
    #vanishing points pp are orgnized in format: [x,y]
    #calculate f, roll, pitch, and yaw using vanishing points
        oVrC = np.array([2, 1])
        oVlC = np.array([2, 1])
        oVrC[0] = oVr[0] - oPrinPt[0]
        oVrC[1] = oPrinPt[1] - oVr[1]
        oVlC[0] = oVl[0] - oPrinPt[0]
        oVlC[1] = oPrinPt[1] - oVl[1]
        fRoll = math.atan2((oVrC[1] - oVlC[1]), (oVrC[0] - oVlC[0]))
        fRoll = fRoll - math.pi if (fRoll > (math.pi / 2)) else fRoll
        fRoll = fRoll + math.pi if (fRoll < -(math.pi / 2)) else fRoll
        oVrCRot = rotPt(oVrC, -fRoll)
        oVlCRot = rotPt(oVlC, -fRoll)

        fF = math.sqrt(-((oVrCRot[1] * oVrCRot[1]) + (oVrCRot[0] * oVlCRot[0])))

        if Config.COORD_SYS_TYP== 0 :
            fPitch = -math.atan2(oVrCRot[1], fF)
            fYaw = -math.atan2(fF, (oVrCRot[0]* math.cos(fPitch)))
        elif Config.COORD_SYS_TYP== 1 :
            fPitch = -math.atan2(oVrCRot[1], fF)
            fYaw = -math.atan2((oVrCRot[0] * math.cos(fPitch)), fF)

        self.CamParam.Fx = fF
        self.CamParam.Fy = fF
        self.CamParam.Cx = oPrinPt[0]
        self.CamParam.Cy = oPrinPt[1]
        self.CamParam.Pitch = fPitch
        self.CamParam.Yaw = fYaw
        self.CamParam.Roll = fRoll
        self.CamParam.Tx = 0

        if Config.COORD_SYS_TYP== 0 :
            self.CamParam.Ty = -fCamHei * Config.LenUnit
            self.CamParam.Tz = 0

        elif Config.COORD_SYS_TYP== 1 :
            self.CamParam.Ty = 0
            self.CamParam.Tz = fCamHei * Config.LenUnit

        self.CamParam.setMatrix_K(fF, fF, oPrinPt[0],oPrinPt[1])
        self.CamParam.setMatrix_R(fRoll, fPitch, fYaw)

        if Config.COORD_SYS_TYP== 0 :
            self.CamParam.setMatrix_T(0, -fCamHei * Config.LenUnit, 0)
        elif Config.COORD_SYS_TYP== 1 :
            self.CamParam.setMatrix_T(0, 0, -fCamHei * Config.LenUnit)
        self.CamParam.calMatrix_P()

#calculates reprojection error based on measurement error compared to ground truth
    def calcReprojErr(self, P):
        voMeasLnSegNdPt = self.MeasLnSegNdPt
        vfMeasLnSegDist = self.MeasLnSegDist
        fReprojErr = 0
        oSt2dPt=0
        oNd2dPt=0
        oSt3dPt=0
        oNd3dPt=0
        for i in range(0, int(len(voMeasLnSegNdPt)/2)):
            oSt2dPt = voMeasLnSegNdPt[i*2]
            oNd2dPt = voMeasLnSegNdPt[i*2+1]
            oSt3dPt = I2WCal(oSt2dPt[0], oSt2dPt[1], 0, 1, P)
            oNd3dPt = I2WCal(oNd2dPt[0], oNd2dPt[1], 0, 1, P)
            fReprojErr += abs(np.linalg.norm(oNd3dPt - oSt3dPt) - vfMeasLnSegDist[i])
        return fReprojErr
###set ParamRng values
    def initEdaParamRng(self,poCamParam):

        #CCamParam::SParamRng sParamRng
        # calculate f, roll, pitch, and yaw by using vanishing points
        oVr = self.init_VP_r
        oVl = self.init_VP_l
        oPrinPt = self.init_PP
        oVrC = np.array([2, 1])
        oVlC = np.array([2, 1])
        oVrC[0] = oVr[0] - oPrinPt[0]
        oVrC[1] = oPrinPt[1] - oVr[1]
        oVlC[0] = oVl[0] - oPrinPt[0]
        oVlC[1] = oPrinPt[1] - oVl[1]
        fRoll = math.atan2((oVrC[1] - oVlC[1]), (oVrC[0] - oVlC[0]))
        fRoll = fRoll - math.pi if (fRoll > (math.pi / 2)) else fRoll
        fRoll = fRoll + math.pi if (fRoll < -(math.pi / 2)) else fRoll
        oVrCRot = rotPt(oVrC, -fRoll)
        oVlCRot = rotPt(oVlC, -fRoll)
        if poCamParam:
            Kmat = poCamParam.getInParamMat()
            fF = (acK[0] + acK[4]) / 2
        else :
            fF = math.sqrt(-((oVrCRot[1] * oVrCRot[1]) + (oVrCRot[0] * oVlCRot[0])))

        if Config.COORD_SYS_TYP == 0:
            fPitch = -math.atan2(oVrCRot[1], fF)
            fYaw = -math.atan2(fF, (oVrCRot[0] * math.cos(fPitch)))
        elif Config.COORD_SYS_TYP == 1:
            fPitch = -math.atan2(oVrCRot[1], fF)
            fYaw = -math.atan2((oVrCRot[0] * math.cos(fPitch)), fF)
        # construct ranges of camera parameters
        self.sParamRng.fFxMax = poCamParam.Mat_K[0, 0] if poCamParam else fF * (1.0 + Config.EDA_RNG_F)
        self.sParamRng.fFxMin = poCamParam.Mat_K[0, 0] if poCamParam else fF * (1.0 - Config.EDA_RNG_F)
        self.sParamRng.fFyMax = poCamParam.Mat_K[1, 1] if poCamParam else fF * (1.0 + Config.EDA_RNG_F)
        self.sParamRng.fFyMin = poCamParam.Mat_K[1, 1] if poCamParam else fF * (1.0 - Config.EDA_RNG_F)
        self.sParamRng.fCxMax = poCamParam.Mat_K[0, 2] if poCamParam else oPrinPt[0] + Config.EDA_RNG_PRIN_PT
        self.sParamRng.fCxMin = poCamParam.Mat_K[0, 2] if poCamParam else oPrinPt[0] - Config.EDA_RNG_PRIN_PT
        self.sParamRng.fCyMax = poCamParam.Mat_K[1, 2] if poCamParam else oPrinPt[1] + Config.EDA_RNG_PRIN_PT
        self.sParamRng.fCyMin = poCamParam.Mat_K[1, 2] if poCamParam else oPrinPt[1] - Config.EDA_RNG_PRIN_PT
        self.sParamRng.fRollMax = fRoll + np.deg2rad(Config.EDA_RNG_ROT_ANG)
        self.sParamRng.fRollMin = fRoll - np.deg2rad(Config.EDA_RNG_ROT_ANG)
        self.sParamRng.fPitchMax = fPitch + np.deg2rad(Config.EDA_RNG_ROT_ANG)
        self.sParamRng.fPitchMin = fPitch - np.deg2rad(Config.EDA_RNG_ROT_ANG)
        self.sParamRng.fYawMax = fYaw + np.deg2rad(Config.EDA_RNG_ROT_ANG)
        self.sParamRng.fYawMin = fYaw - np.deg2rad(Config.EDA_RNG_ROT_ANG)
        self.sParamRng.fTxMax = 0.0
        self.sParamRng.fTxMin = 0.0
        if Config.COORD_SYS_TYP == 0:
            self.sParamRng.fTyMax = -Config.CalCamHeiMin * Config.LenUnit
            self.sParamRng.fTyMin = -Config.CalCamHeiMax * Config.LenUnit
            self.sParamRng.fTzMax = 0.0
            self.sParamRng.fTzMin = 0.0

        elif Config.COORD_SYS_TYP == 1:
            self.sParamRng.fTzMax = Config.CalCamHeiMax * Config.LenUnit
            self.sParamRng.fTzMin = Config.CalCamHeiMin * Config.LenUnit
            self.sParamRng.fTyMax = 0.0
            self.sParamRng.fTyMin = 0.0


    def estEdaParamRng(self, pvoCamParam):
        # input is list of cam param class objects

        nCamParamNum = len(pvoCamParam)
        nParamNum = 10 # means: fx fx cx cy yaw pitch roll tx ty tz
        afParamMean = np.zeros((nParamNum,1))
        afParamData = np.zeros((nParamNum,nCamParamNum))
        afParamVar  = np.zeros((nParamNum,1))

        #CCamParam::SParamRng sParamRng
        # calculate means of parameters
        for iCamParam, ivoCamParam in enumerate(pvoCamParam):
            #(ivoCamParam = pvoCamParam->begin(); ivoCamParam != pvoCamParam->end(); ivoCamParam++):
            afParamData[0,iCamParam] = ivoCamParam.Fx
            afParamData[1,iCamParam] = ivoCamParam.Fy
            afParamData[2,iCamParam] = ivoCamParam.Cx
            afParamData[3,iCamParam] = ivoCamParam.Cy
            afParamData[4,iCamParam] = ivoCamParam.Roll
            afParamData[5,iCamParam] = ivoCamParam.Pitch
            afParamData[6,iCamParam] = ivoCamParam.Yaw
            afParamData[7,iCamParam] = ivoCamParam.Tx
            afParamData[8,iCamParam] = ivoCamParam.Ty
            afParamData[9,iCamParam] = ivoCamParam.Tz

        for i in range(len(afParamMean)):
            afParamMean[i] = np.mean(afParamData[i,:])
            afParamVar[i]=np.std(afParamData[i,:])

        # fx
        iParam = 0
        self.sParamRng.fFxMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fFxMin = afParamMean[iParam] - afParamVar[iParam]
        # fy
        iParam = 1
        self.sParamRng.fFyMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fFyMin = afParamMean[iParam] - afParamVar[iParam]

        iParam = 2
        self.sParamRng.fCxMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fCxMin = afParamMean[iParam] - afParamVar[iParam]

        iParam = 3
        self.sParamRng.fCyMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fCyMin = afParamMean[iParam] - afParamVar[iParam]

        iParam = 4
        self.sParamRng.fRollMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fRollMin = afParamMean[iParam] - afParamVar[iParam]

        iParam = 5
        self.sParamRng.fPitchMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fPitchMin = afParamMean[iParam] - afParamVar[iParam]

        iParam = 6
        self.sParamRng.fYawMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fYawMin = afParamMean[iParam] - afParamVar[iParam]

        iParam = 7
        self.sParamRng.fTxMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fTxMin = afParamMean[iParam] - afParamVar[iParam]

        iParam = 8
        self.sParamRng.fTyMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fTyMin = afParamMean[iParam] - afParamVar[iParam]

        iParam = 9
        self.sParamRng.fTzMax = afParamMean[iParam] + afParamVar[iParam]
        self.sParamRng.fTzMin = afParamMean[iParam] - afParamVar[iParam]


        # estimates vertical vanishing point Vy by computing center of mass

'''
if __name__ == '__main__':
    #Img=np.zeros((1080,1920))
    root = CamCal()
    VanPt=[[300,500],[550,9000]]
    root.process(VanPt)

'''
