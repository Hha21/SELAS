/**
 * 
 */
package activforms.engines;

import activforms.Effector;
import activforms.LoadBalancer;
import activforms.LoadProbe;
import activforms.ModeListener;
//import activforms.ModelProbe;
import activforms.Probe;
import activforms.engine.ActivFORMSEngine;
import activforms.goalmanagement.Goal;
import activforms.goalmanagement.goalmanager.GoalManager;
import service.adaptation.effectors.ConfigurationEffector;
import service.adaptation.effectors.WorkflowEffector;
import tas.configuration.AdaptationEngine;
import tas.configuration.TASStart;
import tas.services.assistance.AssistanceService;

/**
 * @author M. Usman Iftikhar
 * @email muusaa@lnu.se
 *
 */
public class GoalManagementEngine implements AdaptationEngine{

    public ActivFORMSEngine engine;
    Probe probe;
    Effector effector;
    WorkflowEffector workflowEffector;
    ConfigurationEffector configurationEffector;
    private AssistanceService assistanceService;
    private LoadBalancer loadBalancer;
    //LoadProbe loadProbe = null;
    
    public GoalManagementEngine(AssistanceService assistanceService) {
	this.assistanceService = assistanceService;
	workflowEffector = new WorkflowEffector(assistanceService);
	configurationEffector = new ConfigurationEffector(assistanceService);
	ModeListener modeListener = new ModeListener();
	
	try {
	    //String path=TASStart.class.getProtectionDomain().getCodeSource().getLocation().getPath();
	    engine = new ActivFORMSEngine("Regular","resources/models/regular-mode.xml", 9002);
	    engine.setRealTimeUnit(1);
	   	    
	    probe = new Probe(engine);
	    effector = new Effector(engine, workflowEffector, probe);
	    //loadProbe = new LoadProbe(engine);
	    	    
	    loadBalancer = new LoadBalancer();
	    //loadBalancer.setLoadProbe(loadProbe);
	    
	    
	    GoalManager goalManager = engine.getGoalManager();
	    loadBalancer.setLoadProbe(goalManager.getContextProbe());
	    
	    engine.getGoalManager().addModelFromFile("Critical","resources/models/critical-mode.xml");
	    

	    goalManager.addVariable("serverLoad", 0);
	    goalManager.addVariable("THRESHOLD", 50);
	    
	    Goal topGoal = new Goal("Top goal", "");
	    topGoal.addSubGoal(new Goal("", "serverLoad < THRESHOLD", "Regular", modeListener));
	    topGoal.addSubGoal(new Goal("", "serverLoad >= THRESHOLD", "Critical", modeListener));
	    goalManager.addGoalTree(topGoal);
	    
	    goalManager.addModelProperty("Assistance Service Failure Rate", "A[] k.failureRate <= 1");
	    goalManager.addModelProperty("", "A[] Analysis.AdaptationNeeded imply k.currentService != -1 && k.services[k.currentService].status == FAILED");
	    goalManager.addModelProperty("", "Analysis.AdaptationNeeded --> Execution.PlanExecuted");
	    
	} catch (Exception e) {
	    e.printStackTrace();
	}
    }
        
    public void start() {
	    assistanceService.getWorkflowProbe().register(probe);
	    configurationEffector.setMaxRetryAttempts(3);
	    workflowEffector.refreshAllServices();
	    loadBalancer.start();
	    engine.start();
    }
    
    public void stop(){
	loadBalancer.stop();
	assistanceService.getWorkflowProbe().unRegister(probe);
	configurationEffector.setMaxRetryAttempts(0);
	engine.stop();
    }
    
    public LoadBalancer getLoadBalancer(){
    	return this.loadBalancer;
    }
    
    public ActivFORMSEngine getEngine() {
	return engine;
    }
}
