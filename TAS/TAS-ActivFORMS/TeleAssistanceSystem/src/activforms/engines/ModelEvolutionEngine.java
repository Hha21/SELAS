/**
 * 
 */
package activforms.engines;

import activforms.Effector;
import activforms.Probe;
import activforms.engine.ActivFORMSEngine;
import activforms.goalmanagement.goalmanager.GoalManager;
import service.adaptation.effectors.ConfigurationEffector;
import service.adaptation.effectors.WorkflowEffector;
import tas.configuration.AdaptationEngine;
import tas.services.assistance.AssistanceService;

/**
 * @author M. Usman Iftikhar
 * @email muusaa@lnu.se
 *
 */
public class ModelEvolutionEngine implements AdaptationEngine{

    public ActivFORMSEngine engine;
    Probe probe;
    Effector effector;
    WorkflowEffector workflowEffector;
    private AssistanceService assistanceService;
    ConfigurationEffector configurationEffector;
    
    public ModelEvolutionEngine(AssistanceService assistanceService) {
	this.assistanceService = assistanceService;
	workflowEffector = new WorkflowEffector(assistanceService);
	configurationEffector = new ConfigurationEffector(assistanceService);
	try {
	    //String path=getClass().getResource("/models/model-evolution.xml").getPath();
	    //engine = new ActivFORMSEngine("resources/models/model-adaptation.xml", 9001);
	    engine = new ActivFORMSEngine("resources/models/model-evolution.xml", 9001);
	    //engine.setCommittedLocationTime(1000);
	    engine.setRealTimeUnit(1);
	    probe = new Probe(engine);
	    effector = new Effector(engine, workflowEffector, probe);
	    
	    GoalManager goalManager = engine.getGoalManager();
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
	    engine.start();
    }
    
    public void stop(){
	assistanceService.getWorkflowProbe().unRegister(probe);
	configurationEffector.setMaxRetryAttempts(0);
	engine.stop();
    }
    
    public ActivFORMSEngine getEngine() {
	return engine;
    }
}
