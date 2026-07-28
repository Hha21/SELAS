package activforms;

import java.util.Timer;
import java.util.TimerTask;

import javafx.gui.utility.Handler;
import activforms.goalmanagement.probe.ContextProbe;

public class LoadBalancer {
    protected Timer timer;
    int serverLoad = 0;
    boolean flag = true;
    //private LoadProbe loadProbe;
    public Handler handler;
    ContextProbe probe;
    public LoadBalancer() {
	
    }
    
    public void start(){
	timer = new Timer();
	timer.scheduleAtFixedRate(new TickerTask(), 0, 1000);
    }
    
    public void stop(){
	timer.cancel();
    }
    
    public void setLoadProbe(ContextProbe loadProbe){
	this.probe = loadProbe;
    }

    public ContextProbe getLoadProbe(){
    	return this.probe;
    }
    
    private class TickerTask extends TimerTask {

	@Override
	public void run() {
	    if (flag)
		serverLoad += 1;
	    else
		serverLoad -= 1;

	    if (serverLoad >= 100 || serverLoad <= 0)
		flag = !flag;

	    System.out.println("ServerLoad:" + serverLoad);
	    
	    if(handler!=null)
	    	handler.handle(serverLoad);
		
	    //loadProbe.notifyServerLoad(serverLoad);
	    probe.updateData("serverLoad", serverLoad);
	}
    }
    
    
}
