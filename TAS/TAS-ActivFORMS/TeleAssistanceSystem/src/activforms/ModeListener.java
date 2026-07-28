package activforms;

import activforms.goalmanagement.Goal;
import activforms.goalmanagement.GoalClient;

public class ModeListener implements GoalClient{

    @Override
    public void goalStatusChanged(Goal goal) {
	if (goal.isStatus()){
	    System.out.println(goal.getModelKey());
	}
    }

}
