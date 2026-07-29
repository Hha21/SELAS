/**
 * 
 */
package tas.services.assistance;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.HashMap;
import java.util.Map;

import service.adaptation.probes.interfaces.CostProbeInterface;
import service.adaptation.probes.interfaces.WorkflowProbeInterface;
import service.auxiliary.ServiceDescription;
import service.auxiliary.TimeOutError;
import service.utility.SimClock;
import tas.services.log.Log;

/**
 * @author yfruan
 * @email  ry222ad@student.lnu.se
 *
 */
public class AssistanceServiceCostProbe implements WorkflowProbeInterface,CostProbeInterface{

    //String costFilePath="cost.csv";
    
    private static String resultFilePath="results"+File.separator+"result.csv";
    //private static String resultFilePath="result.csv";
    private double totalCost=0;

    private StringBuilder resultBuilder;
    public int workflowInvocationCount=0;
    private Map<String,Double> delays=new HashMap<>();
    // workflowEnded() used to open/write/close a fresh FileWriter on every single step --
    // for a 10,000-step run, 10,000 blocking file-open/close cycles on the same thread
    // driving the workflow loop. One persistent writer, flushed (not closed) per step,
    // removes that per-step I/O cost; still durable since flush() forces it to disk.
    private PrintWriter out;


    static{
    	File file = new File(resultFilePath);
    	if(file.exists() && !file.isDirectory()) {
    		file.delete();
    	}
    }

    public AssistanceServiceCostProbe() {
    	openWriter();
    }

    private void openWriter(){
    	try {
    		out = new PrintWriter(new BufferedWriter(new FileWriter(resultFilePath, true)));
    	} catch (IOException e) {
    		e.printStackTrace();
    	}
    }

    public void reset(){
    	if (out != null) {
    		out.close();
    	}
    	File file = new File(resultFilePath);
    	if(file.exists() && !file.isDirectory()) {
    		file.delete();
    	}
    	openWriter();
    	workflowInvocationCount=0;
    	totalCost=0;
    }
    
    /*
     * (non-Javadoc)
     * 
     * @see service.adaptation.Probe#workflowStarted(java.lang.String, java.lang.Object[])
     */
    @Override
    public void workflowStarted(String qosRequirement, Object[] params) {
    	System.out.println("Probe: workflowStarted");
	    Log.addLog("WorkflowStarted", "Workflow Started monitoring");
    	resultBuilder=new StringBuilder();
    	totalCost=0;
    	workflowInvocationCount++;	    	
    }

    /*
     * (non-Javadoc)
     * 
     * @see service.adaptation.Probe#workflowEnded(java.lang.Object, java.lang.String, java.lang.Object[])
     */
    @Override
    public void workflowEnded(Object result, String qosRequirement, Object[] params) {
    	System.out.println("Probe: workflowEnded");
    	if(result instanceof TimeOutError){
    		System.out.println("WorkflowError!!!");
        	resultBuilder.append(workflowInvocationCount+","+"AssistanceService"+",false,"+totalCost+"\n");
    	}
    	else
        	resultBuilder.append(workflowInvocationCount+","+"AssistanceService"+",true,"+totalCost+"\n");
    	out.println(resultBuilder.toString());
    	out.flush();
    }
	
    /*
     * (non-Javadoc)
     * 
     * @see service.adaptation.Probe#timeout(service.auxiliary.ServiceDescription, java.lang.String, java.lang.Object[])
     */
    @Override
    public void serviceOperationTimeout(ServiceDescription service, String opName, Object[] params) {
    	System.out.println("Probe: timeout");
    	resultBuilder.append(workflowInvocationCount+","+service.getServiceName()+",false\n");
    }

	@Override
	public void serviceCost(ServiceDescription service, String opName, double cost) {
		// TODO Auto-generated method stub
	    String serviceName = service.getServiceName();
		System.out.println("Serivice Cost: "+cost);
		String fullOperation=serviceName+"."+opName;
		Double begin=delays.get(fullOperation);
		//Double end=(Double)(System.nanoTime()/1000000.000);
		Double end=SimClock.getCurrentTime();
		
		totalCost=totalCost+cost;
    	resultBuilder.append(workflowInvocationCount+","+serviceName+",true,"+cost+","+begin+","+(end-begin)+"\n");
	}

	@Override
	public void serviceOperationInvoked(ServiceDescription service,
			String opName, Object[] params) {
		// TODO Auto-generated method stub
		//delays.put(service.getServiceName()+"."+opName, (Double)(System.nanoTime()/1000000.000));
		delays.put(service.getServiceName()+"."+opName, SimClock.getCurrentTime());
	}

	@Override
	public void serviceOperationReturned(ServiceDescription service,
			Object result, String opName, Object[] params) {
		// TODO Auto-generated method stub
		
	}

	@Override
	public void serviceNotFound(String serviceType, String opName) {
	    // TODO Auto-generated method stub
	    
	}
}
