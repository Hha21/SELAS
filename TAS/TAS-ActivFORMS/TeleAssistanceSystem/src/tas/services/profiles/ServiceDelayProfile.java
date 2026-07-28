package tas.services.profiles;

import java.util.Random;

import service.atomic.ServiceProfile;
import service.atomic.ServiceProfileAttribute;
import service.utility.SimClock;
import service.utility.Time;
	
public class ServiceDelayProfile extends ServiceProfile{

	@ServiceProfileAttribute
	public int minDelay;
	
	@ServiceProfileAttribute
	public int maxDelay;
    
	Random random = new Random();
	
	public ServiceDelayProfile(int delay) {
	    minDelay = delay;
	    maxDelay = delay;
	}
	
	@Override
	public boolean preInvokeOperation(String operationName, Object... args) {
	 
		SimClock.increment((random.nextInt(maxDelay - minDelay + 1) + minDelay));
	 
		return true;
	}

	@Override
	public Object postInvokeOperation(String operationName, Object result,
			Object... args) {
		return result;
	}
}
