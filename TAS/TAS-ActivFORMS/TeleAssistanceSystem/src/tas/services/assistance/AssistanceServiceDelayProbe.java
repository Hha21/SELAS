package tas.services.assistance;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.HashMap;
import java.util.Map;

import service.adaptation.probes.interfaces.WorkflowProbeInterface;
import service.auxiliary.ServiceDescription;

public class AssistanceServiceDelayProbe implements WorkflowProbeInterface{

    private static String resultFilePath="results"+File.separator+"delay.csv";    
    private StringBuilder resultBuilder=new StringBuilder();
    
    private Map<String,Long> delays=new HashMap<>();
        
    static{
    	File file = new File(resultFilePath);
    	if(file.exists() && !file.isDirectory()) {
    		file.delete();
    	}
    }
    
    public void reset(){
    	File file = new File(resultFilePath);
    	if(file.exists() && !file.isDirectory()) {
    		file.delete();
    	}
    }
    
	@Override
	public void workflowStarted(String qosRequirement, Object[] params) {
		// TODO Auto-generated method stub
	}

	@Override
	public void serviceOperationInvoked(ServiceDescription service,
			String opName, Object[] params) {
		delays.put(service.getServiceName()+"."+opName, System.currentTimeMillis());
	}

	@Override
	public void serviceOperationReturned(ServiceDescription service,
			Object result, String opName, Object[] params) {
		String fullOperation=service.getServiceName()+"."+opName;
		if(delays.containsKey(fullOperation)){
			Long begin=delays.get(fullOperation);
			Long end=System.currentTimeMillis();
			resultBuilder.append(service.getServiceName()+","+begin+","+(end-begin));
		}
	}

	@Override
	public void serviceOperationTimeout(ServiceDescription service,
			String opName, Object[] params) {
		// TODO Auto-generated method stub
		
	}

	@Override
	public void serviceNotFound(String serviceType, String opName) {
		// TODO Auto-generated method stub
	}

	@Override
	public void workflowEnded(Object result, String qosRequirement,
			Object[] params) {
    	try(
        		PrintWriter out = new PrintWriter(new BufferedWriter(new FileWriter(resultFilePath, true)))) {
        	    out.println(resultBuilder.toString());
        }catch (IOException e) {}
	}

}
