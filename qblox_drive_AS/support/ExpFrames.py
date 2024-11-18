from numpy import ndarray
from abc import ABC
import os
from datetime import datetime
from xarray import Dataset
from qblox_drive_AS.support.QDmanager import QDmanager
from qblox_drive_AS.analysis.Multiplexing_analysis import Multiplex_analyzer
from qblox_drive_AS.support.UserFriend import *
from xarray import open_dataset
from numpy import array, linspace, arange, logspace
from abc import abstractmethod
from qblox_drive_AS.support import init_meas, init_system_atte, shut_down, coupler_zctrl, advise_where_fq
from qblox_drive_AS.support.Pulse_schedule_library import set_LO_frequency, QS_fit_analysis
from quantify_scheduler.helpers.collections import find_port_clock_path


class ExpGovernment(ABC):
    def __init__(self):
        self.QD_path:str = ""
    
    @abstractmethod
    def SetParameters(self,*args,**kwargs):
        pass

    @abstractmethod
    def PrepareHardware(self,*args,**kwargs):
        pass

    @abstractmethod
    def RunMeasurement(self,*args,**kwargs):
        pass

    @abstractmethod
    def RunAnalysis(self,*args,**kwargs):
        pass

    @abstractmethod
    def CloseMeasurement(self,*args,**kwargs):
        pass

    @abstractmethod
    def WorkFlow(self):
        pass








class BroadBand_CavitySearching(ExpGovernment):
    def __init__(self,QD_path:str,data_folder:str=None,JOBID:str=None):
        super().__init__()
        self.QD_path = QD_path
        self.save_dir = data_folder
        self.__raw_data_location:str = ""
        self.JOBID = JOBID

    @property
    def RawDataPath(self):
        return self.__raw_data_location

    def SetParameters(self, target_qs:list,freq_start:float, freq_end:float, freq_pts:int):
        self.counter:int = len(target_qs)
        self.target_qs = target_qs
        self.freq_start = freq_start
        self.freq_end = freq_end
        self.freq_pts = freq_pts
    
    def PrepareHardware(self):
        self.QD_agent, self.cluster, self.meas_ctrl, self.ic, self.Fctrl = init_meas(QuantumDevice_path=self.QD_path)
        # Set the system attenuations
        init_system_atte(self.QD_agent.quantum_device,self.target_qs,ro_out_att=self.QD_agent.Notewriter.get_DigiAtteFor(self.target_qs[len(self.target_qs)-self.counter], 'ro'))
        # Readout select
        qrmRF_slot_idx = int(find_port_clock_path(self.QD_agent.quantum_device.hardware_config(),"q:res",f"{self.target_qs[int(len(self.target_qs)-self.counter)]}.ro")[1][-1])
        self.readout_module = self.cluster.modules[qrmRF_slot_idx-1]
    
    def RunMeasurement(self):
        from qblox_drive_AS.SOP.wideCS import wideCS
        dataset = wideCS(self.readout_module,self.freq_start,self.freq_end,self.freq_pts)
        if self.save_dir is not None:
            self.save_path = os.path.join(self.save_dir,f"BroadBandCS_{datetime.now().strftime('%Y%m%d%H%M%S') if self.JOBID is None else self.JOBID}")
            self.__raw_data_location = self.save_path + ".nc"
            dataset.to_netcdf(self.__raw_data_location)
            self.save_fig_path = self.save_path+".png"
        else:
            self.save_fig_path = None
        
    def CloseMeasurement(self):
        shut_down(self.cluster,self.Fctrl)
        self.counter -= 1


    def RunAnalysis(self,new_QD_dir:str=None):
        """ User callable analysis function pack """
        from qblox_drive_AS.SOP.wideCS import plot_S21
        ds = open_dataset(self.__raw_data_location)

        QD_savior = QDmanager(self.QD_path)
        QD_savior.QD_loader()
        if new_QD_dir is None:
            new_QD_dir = self.QD_path
        else:
            new_QD_dir = os.path.join(new_QD_dir,os.path.split(self.QD_path)[-1])

        plot_S21(ds,self.save_fig_path)
        ds.close()
        QD_savior.QD_keeper(new_QD_dir)


    def WorkFlow(self):
        while self.counter > 0 :
            self.PrepareHardware()

            self.RunMeasurement()

            self.CloseMeasurement()

class Zoom_CavitySearching(ExpGovernment):
    """ Helps you get the **BARE** cavities. """
    def __init__(self,QD_path:str,data_folder:str=None,JOBID:str=None):
        super().__init__()
        self.QD_path = QD_path
        self.save_dir = data_folder
        self.__raw_data_location:str = ""
        self.JOBID = JOBID

    @property
    def RawDataPath(self):
        return self.__raw_data_location

    def SetParameters(self, freq_range:dict, freq_pts:int=100, avg_n:int=100, execution:bool=True):
        """ freq_range: {"q0":[freq_start, freq_end], ...}, sampling function use linspace """
        self.freq_range = {}
        for q in freq_range:
            self.freq_range[q] = linspace(freq_range[q][0], freq_range[q][1], freq_pts)

        self.avg_n = avg_n
        self.execution = execution
        self.target_qs = list(self.freq_range.keys())


    def PrepareHardware(self):
        self.QD_agent, self.cluster, self.meas_ctrl, self.ic, self.Fctrl = init_meas(QuantumDevice_path=self.QD_path)
        # Set the system attenuations
        init_system_atte(self.QD_agent.quantum_device,self.target_qs,ro_out_att=self.QD_agent.Notewriter.get_DigiAtteFor(self.target_qs[0], 'ro'))
        
        
    
    def RunMeasurement(self):
        from qblox_drive_AS.SOP.CavitySpec import QD_RO_init, Cavity_spec
        QD_RO_init(self.QD_agent,self.freq_range)
        dataset = Cavity_spec(self.QD_agent,self.meas_ctrl,self.freq_range,self.avg_n,self.execution)
        if self.execution:
            if self.save_dir is not None:
                self.save_path = os.path.join(self.save_dir,f"zoomCS_{datetime.now().strftime('%Y%m%d%H%M%S') if self.JOBID is None else self.JOBID}")
                self.__raw_data_location = self.save_path + ".nc"
                dataset.to_netcdf(self.__raw_data_location)
                
            else:
                self.save_fig_path = None
        
    def CloseMeasurement(self):
        shut_down(self.cluster,self.Fctrl)


    def RunAnalysis(self,new_QD_dir:str=None):
        """ User callable analysis function pack """
        from qblox_drive_AS.SOP.CavitySpec import CS_ana
        if self.execution:
            ds = open_dataset(self.__raw_data_location)

            QD_savior = QDmanager(self.QD_path)
            QD_savior.QD_loader()
            if new_QD_dir is None:
                new_QD_dir = self.QD_path
            else:
                new_QD_dir = os.path.join(new_QD_dir,os.path.split(self.QD_path)[-1])

            CS_ana(QD_savior,ds,self.save_dir)
            ds.close()
            QD_savior.QD_keeper(new_QD_dir)


    def WorkFlow(self):
    
        self.PrepareHardware()

        self.RunMeasurement()
        
        self.CloseMeasurement()
        
class PowerCavity(ExpGovernment):
    def __init__(self,QD_path:str,data_folder:str=None,JOBID:str=None):
        super().__init__()
        self.QD_path = QD_path
        self.save_dir = data_folder
        self.__raw_data_location:str = ""
        self.JOBID = JOBID

    @property
    def RawDataPath(self):
        return self.__raw_data_location

    def SetParameters(self, freq_span_range:dict, roamp_range:list, roamp_sampling_func:str, freq_pts:int=100, avg_n:int=100, execution:bool=True):
        """ ### Args:
            * freq_span_range: {"q0":[freq_span_start, freq_span_end], ...}, sampling function use linspace\n
            * roamp_range: [amp_start, amp_end, pts]\n
            * roamp_sampling_func (str): 'linspace', 'arange', 'logspace'
        """
        self.freq_range = {}
        self.tempor_freq:list = [freq_span_range,freq_pts] # After QD loaded, use it to set self.freq_range

        self.avg_n = avg_n
        self.execution = execution
        self.target_qs = list(freq_span_range.keys())
        if roamp_sampling_func in ['linspace','logspace','arange']:
            sampling_func:callable = eval(roamp_sampling_func)
        else:
            sampling_func:callable = linspace
        self.roamp_samples = sampling_func(*roamp_range)

    def PrepareHardware(self):
        self.QD_agent, self.cluster, self.meas_ctrl, self.ic, self.Fctrl = init_meas(QuantumDevice_path=self.QD_path)
        # Set the system attenuations
        init_system_atte(self.QD_agent.quantum_device,self.target_qs,ro_out_att=self.QD_agent.Notewriter.get_DigiAtteFor(self.target_qs[0], 'ro'))
        
    def RunMeasurement(self):
        from qblox_drive_AS.SOP.PowCavSpec import PowerDep_spec
        from qblox_drive_AS.SOP.CavitySpec import QD_RO_init
        
        # set self.freq_range
        for q in self.tempor_freq[0]:
            rof = self.QD_agent.quantum_device.get_element(q).clock_freqs.readout()
            self.freq_range[q] = linspace(rof+self.tempor_freq[0][q][0],rof+self.tempor_freq[0][q][1],self.tempor_freq[1])
        QD_RO_init(self.QD_agent,self.freq_range)
        dataset = PowerDep_spec(self.QD_agent,self.meas_ctrl,self.freq_range,self.roamp_samples,self.avg_n,self.execution)
        if self.execution:
            if self.save_dir is not None:
                self.save_path = os.path.join(self.save_dir,f"PowerCavity_{datetime.now().strftime('%Y%m%d%H%M%S') if self.JOBID is None else self.JOBID}")
                self.__raw_data_location = self.save_path + ".nc"
                dataset.to_netcdf(self.__raw_data_location)
                
            else:
                self.save_fig_path = None
        
    def CloseMeasurement(self):
        shut_down(self.cluster,self.Fctrl)


    def RunAnalysis(self,new_QD_dir:str=None):
        """ User callable analysis function pack """
        from qblox_drive_AS.SOP.PowCavSpec import plot_powerCavity_S21
        if self.execution:
            ds = open_dataset(self.__raw_data_location)

            QD_savior = QDmanager(self.QD_path)
            QD_savior.QD_loader()
            if new_QD_dir is None:
                new_QD_dir = self.QD_path
            else:
                new_QD_dir = os.path.join(new_QD_dir,os.path.split(self.QD_path)[-1])

            plot_powerCavity_S21(ds,QD_savior,self.save_dir)
            ds.close()
        # QD_savior.QD_keeper(new_QD_dir)


    def WorkFlow(self):
    
        self.PrepareHardware()

        self.RunMeasurement()

        self.CloseMeasurement()      

class Dressed_CavitySearching(ExpGovernment):
    """ Helps you get the **Dressed** cavities. """
    def __init__(self,QD_path:str,data_folder:str=None,JOBID:str=None):
        super().__init__()
        self.QD_path = QD_path
        self.save_dir = data_folder
        self.__raw_data_location:str = ""
        self.JOBID = JOBID

    @property
    def RawDataPath(self):
        return self.__raw_data_location

    def SetParameters(self, freq_range:dict, ro_amp:dict, freq_pts:int=100, avg_n:int=100, execution:bool=True):
        """ 
        ### Args:\n
        * freq_range: {"q0":[freq_start, freq_end], ...}, sampling function use linspace\n
        * ro_amp: {"q0":0.1, "q2":.... }
        """
        self.freq_range = {}
        for q in freq_range:
            self.freq_range[q] = linspace(freq_range[q][0], freq_range[q][1], freq_pts)
        self.ro_amp = ro_amp
        self.avg_n = avg_n
        self.execution = execution
        self.target_qs = list(self.freq_range.keys())


    def PrepareHardware(self):
        self.QD_agent, self.cluster, self.meas_ctrl, self.ic, self.Fctrl = init_meas(QuantumDevice_path=self.QD_path)
        # Set the system attenuations
        init_system_atte(self.QD_agent.quantum_device,self.target_qs,ro_out_att=self.QD_agent.Notewriter.get_DigiAtteFor(self.target_qs[0], 'ro')) 
        
    
    def RunMeasurement(self):
        from qblox_drive_AS.SOP.CavitySpec import Cavity_spec, QD_RO_init
        QD_RO_init(self.QD_agent,self.freq_range)
        for q in self.ro_amp:
            self.QD_agent.quantum_device.get_element(q).measure.pulse_amp(self.ro_amp[q])
        dataset = Cavity_spec(self.QD_agent,self.meas_ctrl,self.freq_range,self.avg_n,self.execution)
        if self.execution:
            if self.save_dir is not None:
                self.save_path = os.path.join(self.save_dir,f"dressedCS_{datetime.now().strftime('%Y%m%d%H%M%S') if self.JOBID is None else self.JOBID}")
                self.__raw_data_location = self.save_path + ".nc"
                dataset.to_netcdf(self.__raw_data_location)
                
            else:
                self.save_fig_path = None
        
    def CloseMeasurement(self):
        shut_down(self.cluster,self.Fctrl)


    def RunAnalysis(self,new_QD_dir:str=None):
        """ User callable analysis function pack """
        from qblox_drive_AS.SOP.CavitySpec import CS_ana
        if self.execution:
            ds = open_dataset(self.__raw_data_location)

            QD_savior = QDmanager(self.QD_path)
            QD_savior.QD_loader()
            if new_QD_dir is None:
                new_QD_dir = self.QD_path
            else:
                new_QD_dir = os.path.join(new_QD_dir,os.path.split(self.QD_path)[-1])
            for q in self.ro_amp:
                QD_savior.quantum_device.get_element(q).measure.pulse_amp(self.ro_amp[q])
            CS_ana(QD_savior,ds,self.save_dir,keep_bare=False)
            ds.close()
            QD_savior.QD_keeper(new_QD_dir)


    def WorkFlow(self):
    
        self.PrepareHardware()

        self.RunMeasurement()

        self.CloseMeasurement() 
        
class FluxCoupler(ExpGovernment):
    def __init__(self,QD_path:str,data_folder:str=None,JOBID:str=None):
        super().__init__()
        self.QD_path = QD_path
        self.save_dir = data_folder
        self.__raw_data_location:str = ""
        self.JOBID = JOBID

    @property
    def RawDataPath(self):
        return self.__raw_data_location

    def SetParameters(self, freq_span_range:dict, bias_elements:list, flux_range:list, flux_sampling_func:str, freq_pts:int=100, avg_n:int=100, execution:bool=True):
        """ ### Args:
            * freq_span_range: {"q0":[freq_span_start, freq_span_end], ...}, sampling function use linspace\n
            * bias_elements (list): ["c0", "c1",... ]\n
            * flux_range: [amp_start, amp_end, pts]\n
            * flux_sampling_func (str): 'linspace', 'arange', 'logspace'
        """
        self.freq_range = {}
        self.tempor_freq:list = [freq_span_range,freq_pts] # After QD loaded, use it to set self.freq_range
        self.bias_targets = bias_elements
        self.avg_n = avg_n
        self.execution = execution
        self.target_qs = list(freq_span_range.keys())
        if flux_sampling_func in ['linspace','logspace','arange']:
            sampling_func:callable = eval(flux_sampling_func)
        else:
            sampling_func:callable = linspace
        self.flux_samples = sampling_func(*flux_range)

    def PrepareHardware(self):
        self.QD_agent, self.cluster, self.meas_ctrl, self.ic, self.Fctrl = init_meas(QuantumDevice_path=self.QD_path)
        # Set the system attenuations
        init_system_atte(self.QD_agent.quantum_device,self.target_qs,ro_out_att=self.QD_agent.Notewriter.get_DigiAtteFor(self.target_qs[0], 'ro'))

        
    def RunMeasurement(self):
        from qblox_drive_AS.SOP.CouplerFluxSpec import fluxCoupler_spec
        from qblox_drive_AS.SOP.CavitySpec import QD_RO_init
        # set self.freq_range
        for q in self.tempor_freq[0]:
            rof = self.QD_agent.quantum_device.get_element(q).clock_freqs.readout()
            self.freq_range[q] = linspace(rof+self.tempor_freq[0][q][0],rof+self.tempor_freq[0][q][1],self.tempor_freq[1])
        QD_RO_init(self.QD_agent,self.freq_range)
        dataset = fluxCoupler_spec(self.QD_agent,self.meas_ctrl,self.freq_range,self.bias_targets,self.flux_samples,self.avg_n,self.execution)
        if self.execution:
            if self.save_dir is not None:
                self.save_path = os.path.join(self.save_dir,f"FluxCoupler_{datetime.now().strftime('%Y%m%d%H%M%S') if self.JOBID is None else self.JOBID}")
                self.__raw_data_location = self.save_path + ".nc"
                dataset.to_netcdf(self.__raw_data_location)
                
            else:
                self.save_fig_path = None
        
    def CloseMeasurement(self):
        shut_down(self.cluster,self.Fctrl)


    def RunAnalysis(self,new_QD_dir:str=None):
        """ User callable analysis function pack """
        if self.execution:
            ds = open_dataset(self.__raw_data_location)
            for var in ds.data_vars:
                ANA = Multiplex_analyzer("m5")
                if var.split("_")[-1] != 'freq':
                    ANA._import_data(ds,2)
                    ANA._start_analysis(var_name=var)
                    ANA._export_result(self.save_dir)
            ds.close()



    def WorkFlow(self):
    
        self.PrepareHardware()

        self.RunMeasurement()

        self.CloseMeasurement()          

class FluxCavity(ExpGovernment):
    def __init__(self,QD_path:str,data_folder:str=None,JOBID:str=None):
        super().__init__()
        self.QD_path = QD_path
        self.save_dir = data_folder
        self.__raw_data_location:str = ""
        self.JOBID = JOBID

    @property
    def RawDataPath(self):
        return self.__raw_data_location

    def SetParameters(self, freq_span_range:dict, flux_range:list, flux_sampling_func:str, freq_pts:int=100, avg_n:int=100, execution:bool=True):
        """ ### Args:
            * freq_span_range: {"q0":[freq_span_start, freq_span_end], ...}, sampling function use linspace\n
            * flux_range: [amp_start, amp_end, pts]\n
            * flux_sampling_func (str): 'linspace', 'arange', 'logspace'
        """
        self.freq_range = {}
        self.tempor_freq:list = [freq_span_range,freq_pts] # After QD loaded, use it to set self.freq_range
        self.avg_n = avg_n
        self.execution = execution
        self.target_qs = list(freq_span_range.keys())
        if flux_sampling_func in ['linspace','logspace','arange']:
            sampling_func:callable = eval(flux_sampling_func)
        else:
            sampling_func:callable = linspace
        self.flux_samples = sampling_func(*flux_range)

    def PrepareHardware(self):
        self.QD_agent, self.cluster, self.meas_ctrl, self.ic, self.Fctrl = init_meas(QuantumDevice_path=self.QD_path)
        # Set the system attenuations
        init_system_atte(self.QD_agent.quantum_device,self.target_qs,ro_out_att=self.QD_agent.Notewriter.get_DigiAtteFor(self.target_qs[0], 'ro'))
        # bias coupler
        self.Fctrl = coupler_zctrl(self.Fctrl,self.QD_agent.Fluxmanager.build_Cctrl_instructions([cp for cp in self.Fctrl if cp[0]=='c' or cp[:2]=='qc'],'i'))
        
    def RunMeasurement(self):
        from qblox_drive_AS.SOP.FluxCavSpec import FluxCav_spec
        from qblox_drive_AS.SOP.CavitySpec import QD_RO_init
        # set self.freq_range
        for q in self.tempor_freq[0]:
            rof = self.QD_agent.quantum_device.get_element(q).clock_freqs.readout()
            self.freq_range[q] = linspace(rof+self.tempor_freq[0][q][0],rof+self.tempor_freq[0][q][1],self.tempor_freq[1])
        QD_RO_init(self.QD_agent,self.freq_range)
        dataset = FluxCav_spec(self.QD_agent,self.meas_ctrl,self.Fctrl,self.freq_range,self.flux_samples,self.avg_n,self.execution)
        if self.execution:
            if self.save_dir is not None:
                self.save_path = os.path.join(self.save_dir,f"FluxCavity_{datetime.now().strftime('%Y%m%d%H%M%S') if self.JOBID is None else self.JOBID}")
                self.__raw_data_location = self.save_path + ".nc"
                dataset.to_netcdf(self.__raw_data_location)
                
            else:
                self.save_fig_path = None
        
    def CloseMeasurement(self):
        shut_down(self.cluster,self.Fctrl)


    def RunAnalysis(self,new_QD_dir:str=None):
        """ User callable analysis function pack """
        from qblox_drive_AS.SOP.FluxCavSpec import update_flux_info_in_results_for
        if self.execution:
            QD_savior = QDmanager(self.QD_path)
            QD_savior.QD_loader()
            if new_QD_dir is None:
                new_QD_dir = self.QD_path
            else:
                new_QD_dir = os.path.join(new_QD_dir,os.path.split(self.QD_path)[-1])

            ds = open_dataset(self.__raw_data_location)
            answer = {}
            for var in ds.data_vars:
                if str(var).split("_")[-1] != 'freq':
                    ANA = Multiplex_analyzer("m6")
                    ANA._import_data(ds,2)
                    ANA._start_analysis(var_name=var)
                    ANA._export_result(self.save_dir)
                    answer[var] = ANA.fit_packs
            ds.close()
            permi = mark_input(f"What qubit can be updated ? {list(answer.keys())}/ all/ no ").lower()
            if permi in list(answer.keys()):
                update_flux_info_in_results_for(QD_savior,permi,answer[permi])
                QD_savior.QD_keeper(new_QD_dir)
            elif permi in ["all",'y','yes']:
                for q in list(answer.keys()):
                    update_flux_info_in_results_for(QD_savior,q,answer[q])
                QD_savior.QD_keeper(new_QD_dir)
            else:
                print("Updating got denied ~")



    def WorkFlow(self):
    
        self.PrepareHardware()

        self.RunMeasurement()

        self.CloseMeasurement()   

class IQ_references(ExpGovernment):
    """ Helps you get the **Dressed** cavities. """
    def __init__(self,QD_path:str,data_folder:str=None,JOBID:str=None):
        super().__init__()
        self.QD_path = QD_path
        self.save_dir = data_folder
        self.__raw_data_location:str = ""
        self.JOBID = JOBID

    @property
    def RawDataPath(self):
        return self.__raw_data_location

    def SetParameters(self, ro_amp_factor:dict, shots:int=100, execution:bool=True):
        """ 
        ### Args:\n
        * ro_amp_factor: {"q0":1.2, "q2":.... }, new ro amp = ro_amp*ro_amp_factor
        """
        self.ask_save:bool = False
        self.ro_amp = ro_amp_factor
        self.avg_n = shots
        self.execution = execution
        self.target_qs = list(self.ro_amp.keys())
        for i in self.ro_amp:
            if self.ro_amp[i] != 1:
                self.ask_save = True


    def PrepareHardware(self):
        self.QD_agent, self.cluster, self.meas_ctrl, self.ic, self.Fctrl = init_meas(QuantumDevice_path=self.QD_path)
        # Set the system attenuations
        init_system_atte(self.QD_agent.quantum_device,self.target_qs,ro_out_att=self.QD_agent.Notewriter.get_DigiAtteFor(self.target_qs[0], 'ro')) 
        # bias coupler
        self.Fctrl = coupler_zctrl(self.Fctrl,self.QD_agent.Fluxmanager.build_Cctrl_instructions([cp for cp in self.Fctrl if cp[0]=='c' or cp[:2]=='qc'],'i'))
        for q in self.ro_amp:
            self.Fctrl[q](float(self.QD_agent.Fluxmanager.get_proper_zbiasFor(target_q=q)))
    
    def RunMeasurement(self):
        from qblox_drive_AS.SOP.RefIQ import Single_shot_ref_spec
       

        dataset = Single_shot_ref_spec(self.QD_agent,self.ro_amp,self.avg_n,self.execution)
        if self.execution:
            if self.save_dir is not None:
                self.save_path = os.path.join(self.save_dir,f"IQref_{datetime.now().strftime('%Y%m%d%H%M%S') if self.JOBID is None else self.JOBID}")
                self.__raw_data_location = self.save_path + ".nc"
                dataset.to_netcdf(self.__raw_data_location)
            else:
                self.save_fig_path = None
        
    def CloseMeasurement(self):
        shut_down(self.cluster,self.Fctrl)


    def RunAnalysis(self,new_QD_dir:str=None):
        """ User callable analysis function pack """
        from qblox_drive_AS.SOP.RefIQ import IQ_ref_ana
        if self.execution:
            ds = open_dataset(self.__raw_data_location)

            QD_savior = QDmanager(self.QD_path)
            QD_savior.QD_loader()
            if new_QD_dir is None:
                new_QD_dir = self.QD_path
            else:
                new_QD_dir = os.path.join(new_QD_dir,os.path.split(self.QD_path)[-1])
            
            answer = {}
            for q in ds.data_vars:
                answer[q] = IQ_ref_ana(ds,q,self.save_dir)
            ds.close()
            if self.ask_save:
                permi = mark_input(f"What qubit can be updated ? {list(answer.keys())}/ all/ no ").lower()
                if permi in list(answer.keys()):
                    QD_savior.memo_refIQ({permi:answer[permi]})
                    QD_savior.QD_keeper(new_QD_dir)
                elif permi in ["all",'y','yes']:
                    QD_savior.memo_refIQ(answer)
                    QD_savior.QD_keeper(new_QD_dir)
                else:
                    print("Updating got denied ~")
            else:
                QD_savior.QD_keeper(new_QD_dir)


    def WorkFlow(self):
    
        self.PrepareHardware()

        self.RunMeasurement()

        self.CloseMeasurement() 

class PowerConti2tone(ExpGovernment):
    def __init__(self,QD_path:str,data_folder:str=None,JOBID:str=None):
        super().__init__()
        self.QD_path = QD_path
        self.save_dir = data_folder
        self.__raw_data_location:str = ""
        self.JOBID = JOBID

    @property
    def RawDataPath(self):
        return self.__raw_data_location

    def SetParameters(self, freq_range:dict, xyl_range:list, xyl_sampling_func:str, freq_pts:int=100, avg_n:int=100, ro_xy_overlap:bool=False, execution:bool=True):
        """ ### Args:
            * freq_range: {"q0":[freq_start, freq_end], ...}, sampling function use linspace\n
                * if someone is 0 like {"q0":[0]}, system will calculate an advised value.
            * flux_range: [amp_start, amp_end, pts], if only one value inside, we only use that value. \n
            * flux_sampling_func (str): 'linspace', 'arange', 'logspace'
        """
        self.freq_range = {}
        self.overlap:bool = ro_xy_overlap
        self.f_pts = freq_pts
        for q in freq_range:
            if len(freq_range[q]) == 1 and freq_range[q][0] == 0:
                self.freq_range[q] = freq_range[q][0]
            else:
                self.freq_range[q] = linspace(freq_range[q][0],freq_range[q][1],freq_pts)
        
        self.avg_n = avg_n
        self.execution = execution
        self.target_qs = list(freq_range.keys())
        if xyl_sampling_func in ['linspace','logspace','arange']:
            sampling_func:callable = eval(xyl_sampling_func)
        else:
            sampling_func:callable = linspace
        if len(xyl_range) != 1:
            self.xyl_samples = list(sampling_func(*xyl_range))
        else:
            self.xyl_samples = list(xyl_range)

    def PrepareHardware(self):
        self.QD_agent, self.cluster, self.meas_ctrl, self.ic, self.Fctrl = init_meas(QuantumDevice_path=self.QD_path)
        # Set the system attenuations
        init_system_atte(self.QD_agent.quantum_device,self.target_qs,ro_out_att=self.QD_agent.Notewriter.get_DigiAtteFor(self.target_qs[0], 'ro'))
        # bias coupler
        self.Fctrl = coupler_zctrl(self.Fctrl,self.QD_agent.Fluxmanager.build_Cctrl_instructions([cp for cp in self.Fctrl if cp[0]=='c' or cp[:2]=='qc'],'i'))
        # set driving LO and offset bias
        for q in self.freq_range:
            self.Fctrl[q](float(self.QD_agent.Fluxmanager.get_proper_zbiasFor(target_q=q)))
            if isinstance(self.freq_range[q],ndarray):
                print(f"{q} LO @ {max(self.freq_range[q])}")
                set_LO_frequency(self.QD_agent.quantum_device,q=q,module_type='drive',LO_frequency=max(self.freq_range[q]))
        
    def RunMeasurement(self):
        from qblox_drive_AS.SOP.Cnti2Tone import Two_tone_spec
        # set self.freq_range
        for q in self.freq_range:
            if not isinstance(self.freq_range[q],ndarray):
                advised_fq = advise_where_fq(self.QD_agent,q,self.QD_agent.Notewriter.get_sweetGFor(q)) 
                eyeson_print(f"fq advice for {q} @ {round(advised_fq*1e-9,4)} GHz")
                IF_minus = self.QD_agent.Notewriter.get_xyIFFor(q)
                if advised_fq-IF_minus < 2e9:
                    raise ValueError(f"Attempting to set {q} driving LO @ {round((advised_fq-IF_minus)*1e-9,1)} GHz")
                set_LO_frequency(self.QD_agent.quantum_device,q=q,module_type='drive',LO_frequency=advised_fq-IF_minus)
                self.freq_range[q] = linspace(advised_fq-IF_minus-500e6,advised_fq-IF_minus,self.f_pts)

        dataset = Two_tone_spec(self.QD_agent,self.meas_ctrl,self.freq_range,self.xyl_samples,self.avg_n,self.execution,self.overlap)
        if self.execution:
            if self.save_dir is not None:
                self.save_path = os.path.join(self.save_dir,f"PowerCnti2tone_{datetime.now().strftime('%Y%m%d%H%M%S') if self.JOBID is None else self.JOBID}")
                self.__raw_data_location = self.save_path + ".nc"
                dataset.to_netcdf(self.__raw_data_location)
                
            else:
                self.save_fig_path = None
        
    def CloseMeasurement(self):
        shut_down(self.cluster,self.Fctrl)

    def RunAnalysis(self,new_QD_dir:str=None):
        """ User callable analysis function pack """
        from qblox_drive_AS.SOP.Cnti2Tone import update_2toneResults_for
        if self.execution:
            QD_savior = QDmanager(self.QD_path)
            QD_savior.QD_loader()
            if new_QD_dir is None:
                new_QD_dir = self.QD_path
            else:
                new_QD_dir = os.path.join(new_QD_dir,os.path.split(self.QD_path)[-1])

            ds = open_dataset(self.__raw_data_location)
            for var in ds.data_vars:
                if str(var).split("_")[-1] != 'freq':
                    ANA = Multiplex_analyzer("m8")     
                    ANA._import_data(ds,2,self.QD_agent.refIQ[var] if self.QD_agent.rotate_angle[var] == 0 else [self.QD_agent.rotate_angle[var]],QS_fit_analysis)
                    ANA._start_analysis(var_name=var)
                    ANA._export_result(self.save_dir)
                    if ANA.fit_packs != {}:
                        analysis_result = QS_fit_analysis(ANA.fit_packs[var]["contrast"],f=ANA.fit_packs[var]["xyf_data"])
                        update_2toneResults_for(QD_savior,var,{str(var):analysis_result},ANA.xyl[0])
            ds.close()
            QD_savior.QD_keeper(new_QD_dir)

    def WorkFlow(self):
    
        self.PrepareHardware()

        self.RunMeasurement()

        self.CloseMeasurement() 

