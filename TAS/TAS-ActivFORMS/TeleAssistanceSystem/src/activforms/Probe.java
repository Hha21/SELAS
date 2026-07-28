package activforms;

import java.io.PrintWriter;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;

import activforms.engine.ActivFORMSEngine;
import service.adaptation.probes.interfaces.WorkflowProbeInterface;
import service.auxiliary.ServiceDescription;
import service.auxiliary.TimeOutError;

public class Probe implements WorkflowProbeInterface{
    
    ActivFORMSEngine engine;
    int serviceSelected, serviceSucceed, serviceFailed, AS_Started, AS_Succeed, AS_Failed;
    AtomicBoolean adaptationDone = new AtomicBoolean(false);
    
    public Probe(ActivFORMSEngine engine) {
	this.engine = engine;
	
	serviceSelected = engine.getChannel("service_Selected");
	serviceSucceed = engine.getChannel("service_Succeed");
	serviceFailed = engine.getChannel("service_Failed");
	
	AS_Started = engine.getChannel("AS_started");
	AS_Succeed = engine.getChannel("AS_succeed");
	AS_Failed = engine.getChannel("AS_failed");
    }

    @Override
    public void serviceOperationInvoked(ServiceDescription service, String opName, Object[] params) {
	engine.send(serviceSelected, "serviceId = " + service.getRegisterID());
    }

    @Override
    public void serviceOperationReturned(ServiceDescription service, Object result, String opName, Object[] params) {
	engine.send(serviceSucceed, "serviceId = " + service.getRegisterID());
    }
    long times[] = new long[1000];
    int i = 0, j = 0;
    @Override
    public void serviceOperationTimeout(ServiceDescription service, String opName, Object[] params) {
	adaptationDone.set(false);
	long start = System.currentTimeMillis();
	engine.send(serviceFailed, "serviceId=" + service.getRegisterID());
	synchronized (engine) {
	    System.err.println("Service Failed. Waiting " + service.getServiceName());
	    try {
		while(!adaptationDone.get())
		    engine.wait();
	    } catch (InterruptedException e) {
		e.printStackTrace();
	    }
		long end = System.currentTimeMillis();
		times[i++] = end - start;
		if (i == 1000) {
		    System.err.println("done 1000 times.." + j);
		    i = 0;
	
		    try {
			PrintWriter writer = new PrintWriter("/Users/muiadmin/Documents/times" + j++ + ".txt", "UTF-8");
			writer.println(Arrays.toString(times));
			writer.close();
		    } catch (Exception e) {
			e.printStackTrace();
			System.err.println("Verification times: " + Arrays.toString(times));
		    }
	
		    System.err.println("VerificationTime printed");
	
		}
	}
    }

    @Override
    public void workflowStarted(String qosRequirement, Object[] params) {
	engine.send(AS_Started);
    }

    @Override
    public void workflowEnded(Object result, String qosRequirement, Object[] params) {
	if (result instanceof TimeOutError){
	    engine.send(AS_Failed);
	}
	else {
	    engine.send(AS_Succeed);
	}
    }

    public void setAdaptationDone(boolean adaptationDone) {
	this.adaptationDone.set(adaptationDone);
    }

    @Override
    public void serviceNotFound(String serviceType, String opName) {
    }
}
