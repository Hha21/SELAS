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
public class ModelAdaptationEngine implements AdaptationEngine{

    public ActivFORMSEngine engine;
    Probe probe;
    Effector effector;
    WorkflowEffector workflowEffector;
    ConfigurationEffector configurationEffector;
    private AssistanceService assistanceService;
    
    public ModelAdaptationEngine(AssistanceService assistanceService) {
	this.assistanceService = assistanceService;
	workflowEffector = new WorkflowEffector(assistanceService);
	configurationEffector = new ConfigurationEffector(assistanceService);
	
	try {
	    // Initialize ActivFORMS
	    
	    //String path=getClass().getResource("/resources/models/model-adaptation.xml").getPath();
	    engine = new ActivFORMSEngine("resources/models/model-adaptation.xml", 9000);

	    //engine = new ActivFORMSEngine("/Users/muiadmin/Dropbox/TAS-ActivFORMS/code/TeleAssistanceSystem/resources/models/model-adaptation.xml", 9000);
	    engine.setRealTimeUnit(1);
	    
	    // Set Probe and Effector
	    probe = new Probe(engine);
	    effector = new Effector(engine, workflowEffector, probe);
	    
	    // Add runtime properties to be checked by ActivFORMS
	    GoalManager goalManager = engine.getGoalManager();
	    goalManager.addModelProperty("Assistance Service Failure Rate", "A[] k.failureRate <= 1");
	   // goalManager.addModelProperty("", "A[] Analysis.AdaptationNeeded imply k.currentService != -1 && k.services[k.currentService].status == FAILED");
	    goalManager.addModelProperty("", "Analysis.AdaptationNeeded --> Execution.PlanExecuted");
	    
	} catch (Exception e) {
	    e.printStackTrace();
	}
    }
    
    /**
     * This method starts the adaptation engine
     */
    public void start() {
	    assistanceService.getWorkflowProbe().register(probe);
	    configurationEffector.setMaxRetryAttempts(3);
	    workflowEffector.refreshAllServices();
	    engine.start();
    }
    
    /**
     * This method stops the adaptation engine and remove any configuration associated with it.
     */
    public void stop(){
	assistanceService.getWorkflowProbe().unRegister(probe);
	configurationEffector.setMaxRetryAttempts(0);
	engine.stop();
    }
}
