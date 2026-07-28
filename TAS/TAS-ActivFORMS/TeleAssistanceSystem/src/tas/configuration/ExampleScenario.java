/**
 * 
 */
package tas.configuration;

import service.adaptation.effectors.WorkflowEffector;
import tas.adaptation.simple.MyAdaptationEngine;
import tas.adaptation.simple.MyProbe;
import tas.services.assistance.AssistanceService;

/**
 * @author M. Usman Iftikhar
 * @email muusaa@lnu.se
 *
 */
public class ExampleScenario implements AdaptationEngine {

    MyProbe myProbe;
    WorkflowEffector myEffector;
    AssistanceService assistanceService;

    public ExampleScenario(AssistanceService assistanceService) {
	this.assistanceService = assistanceService;
	myProbe = new MyProbe();
	myEffector = new WorkflowEffector(assistanceService);
	MyAdaptationEngine myAdaptationEngine = new MyAdaptationEngine(myProbe, myEffector);
    }

    @Override
    public void start() {
	assistanceService.getWorkflowProbe().register(myProbe);
	myEffector.refreshAllServices();
    }
    @Override
    public void stop() {
	assistanceService.getWorkflowProbe().unRegister(myProbe);
    }
}
