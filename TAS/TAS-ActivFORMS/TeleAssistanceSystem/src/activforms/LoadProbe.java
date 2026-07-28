package activforms;

import javafx.gui.utility.Handler;
import activforms.engine.ActivFORMSEngine;

public class LoadProbe {

    ActivFORMSEngine engine;
    int load_changed;
    
    public Handler handler;
    
    public LoadProbe(ActivFORMSEngine engine){
	this.engine = engine;
	
	load_changed = engine.getChannel("load_changed");
    }
    
    public void notifyServerLoad(int serverLoad) {
    	if(handler!=null)
    		handler.handle(serverLoad);
    	engine.send(load_changed, "serverLoad = " + serverLoad);
    }

}
