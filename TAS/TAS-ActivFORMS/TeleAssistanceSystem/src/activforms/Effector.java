package activforms;

import java.util.HashMap;

import service.adaptation.effectors.WorkflowEffector;
import activforms.engine.ActivFORMSEngine;
import activforms.engine.Synchronizer;

public class Effector extends Synchronizer {

    ActivFORMSEngine engine;
    WorkflowEffector workflowEffector;
    Probe probe;
    int selectAlternativeService, noServiceAvailable;

    public Effector(ActivFORMSEngine engine, WorkflowEffector workflowEffector, Probe probe) {
	this.probe = probe;
	this.engine = engine;

	this.workflowEffector = workflowEffector;

	selectAlternativeService = engine.getChannel("selectAlternativeService");
	noServiceAvailable = engine.getChannel("noServiceAvailable");

	engine.register(selectAlternativeService, this, "alternativeServiceId", "serviceId");
	engine.register(noServiceAvailable, this, "serviceId");
    }

    @Override
    public void receive(int channel, HashMap<String, Object> data) {
	if (channel == selectAlternativeService) {
	    int preferredServiceId = (int) data.get("alternativeServiceId");
	    int serviceId = (int) data.get("serviceId");

	    updateServiceDescription(serviceId, false);

	    if (preferredServiceId != 0) {
		updateServiceDescription(preferredServiceId, true);
	    }
	} else if (channel == noServiceAvailable) {
	    workflowEffector.stopRetrying();
	}

	System.err.println("Adaptation performed");
	synchronized (engine) {
	    probe.setAdaptationDone(true);
	    engine.notifyAll();
	}
    }

    /**
     * Update custom property of a service description in the list of available services
     */
    public void updateServiceDescription(int serviceId, boolean prefferedValue) {
	workflowEffector.updateServiceCustomProperty(serviceId, "preferred", prefferedValue);
    }
}
