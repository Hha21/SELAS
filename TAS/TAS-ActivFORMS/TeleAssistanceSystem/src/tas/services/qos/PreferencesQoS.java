package tas.services.qos;

import java.util.HashMap;
import java.util.List;
import java.util.Random;

import service.auxiliary.ServiceDescription;
import service.workflow.AbstractQoSRequirement;

public class PreferencesQoS implements AbstractQoSRequirement {

    Random rand = new Random();
    MinCostQoS minCostQoS = new MinCostQoS();

    @Override
    public ServiceDescription applyQoSRequirement(List<ServiceDescription> serviceDescriptions, String opName, Object[] params) {

	HashMap<String, Object> customProperties;
	// Search Preferred Service
	for (ServiceDescription serviceDescription : serviceDescriptions) {
	    customProperties = serviceDescription.getCustomProperties();
	    if (customProperties.containsKey("preferred")) {
		boolean value = (boolean) customProperties.remove("preferred");
		if (value)
		    return serviceDescription;
	    }
	}

	// If there is no preferred service found then select a service with minimum cost
	return minCostQoS.applyQoSRequirement(serviceDescriptions, opName, params);
    }
}
