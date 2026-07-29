package application.view.controller;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import service.auxiliary.ServiceDescription;
import service.registry.ServiceRegistry;
import javafx.collections.FXCollections;
import javafx.scene.chart.CategoryAxis;
import javafx.scene.chart.LineChart;
import javafx.scene.chart.NumberAxis;
import javafx.scene.chart.ScatterChart;
import javafx.scene.chart.StackedBarChart;
import javafx.scene.chart.XYChart;
import javafx.scene.chart.XYChart.Data;
import javafx.scene.layout.AnchorPane;
import javafx.scene.paint.Color;
import javafx.scene.shape.Rectangle;

public class ChartController {
	AnchorPane reliabilityChartPane;
	AnchorPane costChartPane;
	AnchorPane performanceChartPane;
	AnchorPane invCostChartPane;

	ScatterChart<Number,String> reliabilityChart;
	StackedBarChart<String,Number> performanceChart;
	LineChart<Number,Number> costChart;
	LineChart<Number,Number> invCostChart;


	AnchorPane avgReliabilityChartPane;
	AnchorPane avgCostChartPane;
	AnchorPane avgPerformanceChartPane;
    AnchorPane invRateChartPane;

	LineChart<Number,Number> avgCostChart;
	LineChart<Number,Number> avgPerformanceChart;
	LineChart<Number,Number> avgReliabilityChart;
	LineChart<Number,Number> invRateChart;

	LinkedHashMap<String,String> serviceTypes;


    protected LinkedHashMap<Integer,Double> failureRates;
    protected LinkedHashMap<Integer,Double> responseTimes;
    protected LinkedHashMap<Integer,Double> costs;
    protected LinkedHashMap<Integer,Map<String,Double>> invocationRates;



	public ChartController(AnchorPane reliabilityChartPane,AnchorPane costChartPane,AnchorPane performanceChartPane, AnchorPane invCostChartPane,
			AnchorPane avgReliabilityChartPane, AnchorPane avgCostChartPane, AnchorPane avgPerformanceChartPane,AnchorPane invRateChartPane,
			LinkedHashMap<String,String> serviceTypes){
		this.reliabilityChartPane=reliabilityChartPane;
		this.costChartPane=costChartPane;
		this.performanceChartPane=performanceChartPane;
		this.invCostChartPane=invCostChartPane;

		this.avgCostChartPane=avgCostChartPane;
		this.avgPerformanceChartPane=avgPerformanceChartPane;
		this.avgReliabilityChartPane=avgReliabilityChartPane;
		this.invRateChartPane=invRateChartPane;

		this.serviceTypes=serviceTypes;

	}

	// Was: each method below re-opened and re-read the whole result.csv file independently
	// (9 read-loops total across this class), all running synchronously on the JavaFX
	// Application Thread via the caller's Platform.runLater -- for a long run (tens of
	// thousands of CSV lines), this froze the UI right when the run finished. Callers now
	// read the file once and pass the lines here, reused across all of them.
	//
	// That fix alone wasn't enough for very long runs (e.g. 10,000 steps): these 4 methods
	// create one JavaFX node per raw invocation (a Rectangle with an active property binding,
	// in generateReliabilityChart's case) -- tens of thousands of live scene-graph nodes,
	// synchronously on the FX thread, is itself the dominant cost, not the file I/O.
	// generateAvgCharts's charts stay bounded regardless of maxSteps (bucketed by slice), so
	// only these raw per-invocation charts are skipped above the threshold.
	//
	// Temporarily disabled (ENABLE_RAW_CHART_LIMIT=false) at user request -- flip back to
	// true to restore the skip if a long run freezes the GUI again.
	private static final boolean ENABLE_RAW_CHART_LIMIT = false;
	private static final int RAW_CHART_MAX_STEPS = 2000;

	public void generateCharts(List<String> lines, int maxSteps){
		if (ENABLE_RAW_CHART_LIMIT && maxSteps > RAW_CHART_MAX_STEPS) {
			System.out.println("Skipping per-invocation charts: " + maxSteps + " steps exceeds "
					+ RAW_CHART_MAX_STEPS + " (one JavaFX node per invocation doesn't scale here). "
					+ "The Avg* charts and tables are unaffected.");
			return;
		}
		this.generateCostChart(lines, maxSteps);
		this.generateInvCostChart(lines, maxSteps);
		this.generatePerformanceChart(lines, maxSteps);
		this.generateReliabilityChart(lines, maxSteps);
	}

	private void generateInvRateChart(List<String> lines, int maxSteps,int slice){
		try{
			invocationRates=new LinkedHashMap<>();

			invRateChartPane.getChildren().clear();

			int maximum=maxSteps/slice;

			NumberAxis xAxis = new NumberAxis("Sliced Invocations",0,maximum,1);
			if(maximum>=100)
				xAxis.setTickUnit(maximum/20);

			NumberAxis yAxis = new NumberAxis();

			invRateChart=new LineChart<Number,Number>(xAxis,yAxis);
			invRateChartPane.getChildren().add(invRateChart);
			invRateChart.prefWidthProperty().bind(invRateChartPane.widthProperty());
			invRateChart.prefHeightProperty().bind(invRateChartPane.heightProperty());

			//invRateChart.setLegendVisible(false);
			invRateChart.getData().clear();

			Map<String,XYChart.Series<Number,Number>> seriesMap = new LinkedHashMap<>();

			Map<String,Double> sumMap=new LinkedHashMap<>();   // service type
			Map<String,Double> countMap=new LinkedHashMap<>();  // service name

			int count=0;

			for(String line:lines){
				String[] str=line.split(",");
				if(str.length>=3){
					String service=str[1];
					if(!service.equals("AssistanceService")){
						if(!countMap.containsKey(service)){
							countMap.put(service, 0.0);
							if(!sumMap.containsKey(serviceTypes.get(service)))
								sumMap.put(serviceTypes.get(service), 0.0);
						}
					}
				}
			}

			/*
			for(String serviceName:serviceTypes.keySet()){
				countMap.put(serviceName, 0.0);
				if(!sumMap.containsKey(serviceTypes.get(serviceName)))
					sumMap.put(serviceTypes.get(serviceName), 0.0);
			}*/

	        for(String line:lines){
				String[] str=line.split(",");

				if(str.length>=3){

					String service=str[1];

					if(service.equals("AssistanceService")){

						count++;

						if(count%slice==0){

							for(String key:countMap.keySet()){

								String type=serviceTypes.get(key);

								if(!seriesMap.containsKey(key)){
									XYChart.Series<Number,Number> series=new XYChart.Series<>();
									series.getData().add(new Data<Number, Number>(0,0));
									series.setName(key);
									seriesMap.put(key, series);

									Map<String,Double> rates=new HashMap<>();
									rates.put(key, 0.0);
									invocationRates.put(0, rates);
								}

								seriesMap.get(key).getData().add(new Data<Number, Number>(count/slice,countMap.get(key)/sumMap.get(type)));

								if(!invocationRates.containsKey(count))
									invocationRates.put(count, new HashMap<>());
								invocationRates.get(count).put(key, countMap.get(key)/sumMap.get(type));

								countMap.put(key, 0.0);
							}

							for(String type:sumMap.keySet()){
								sumMap.put(type, 0.0);
							}

						}
					}
					else{
						countMap.put(service, (countMap.get(service)+1));
						String serviceType=serviceTypes.get(service);
						sumMap.put(serviceType, (sumMap.get(serviceType)+1));
					}

				}
			}

			yAxis.setLabel("Invocation Rate");
			yAxis.setLowerBound(0);
			yAxis.setTickUnit(10);

			invRateChart.getData().addAll(seriesMap.values());
		}
		catch(Exception e){
			e.printStackTrace();
		}
	}

	public void generateAvgCharts(List<String> lines, int maxSteps,int slice){
		this.generateAvgCostChart(lines, maxSteps,slice);
		this.generateAvgPerformanceChart(lines, maxSteps,slice);
		this.generateAvgReliabilityChart(lines, maxSteps,slice);
		this.generateInvRateChart(lines, maxSteps, slice);
	}

	private void generateAvgReliabilityChart(List<String> lines,int maxSteps,int slice){
		try{

			failureRates=new LinkedHashMap<>();
			failureRates.put(0, 0.0);

		    avgReliabilityChartPane.getChildren().clear();

			XYChart.Series<Number,Number> series = new XYChart.Series<>();

			int maximum=maxSteps/slice;

			NumberAxis xAxis = new NumberAxis("Sliced Invocations",0,maximum,1);

			if(maximum>=100)
				xAxis.setTickUnit(maximum/20);

			NumberAxis yAxis = new NumberAxis();

			avgReliabilityChart=new LineChart<Number,Number>(xAxis,yAxis);
			avgReliabilityChartPane.getChildren().add(avgReliabilityChart);
			avgReliabilityChart.prefWidthProperty().bind(avgReliabilityChartPane.widthProperty());
			avgReliabilityChart.prefHeightProperty().bind(avgReliabilityChartPane.heightProperty());

			avgReliabilityChart.setLegendVisible(false);
			avgReliabilityChart.getData().clear();

			//double maxRate=0;
			//double rate=0;
			//double totalRate=0;
			int count=0;
			double successCount=0;

			series.getData().clear();
			series.getData().add(new Data<Number, Number>(0,0));

	        for(String line:lines){
				String[] str=line.split(",");

				if(str.length>=3){


					if(str[1].equals("AssistanceService")){

						count++;

						if(Boolean.parseBoolean(str[2])){
							successCount++;
						}

						if(count%slice==0){
							series.getData().add(new Data<Number, Number>(count/slice,(slice-successCount)/slice));
							failureRates.put(count,(slice-successCount)/slice);
							successCount=0;
						}

					}

				}
			}

			yAxis.setLabel("Average Failure Rate");
			yAxis.setLowerBound(0);
			//yAxis.setUpperBound(maxTime);
			yAxis.setTickUnit(10);

			avgReliabilityChart.getData().add(series);
		}
		catch(Exception e){
			e.printStackTrace();
		}
	}

	private void generateAvgPerformanceChart(List<String> lines,int maxSteps,int slice){
		try{

			responseTimes=new LinkedHashMap<>();
			responseTimes.put(0, 0.0);

		    avgPerformanceChartPane.getChildren().clear();

			XYChart.Series<Number,Number> series = new XYChart.Series<>();

			int maximum=maxSteps/slice;

			NumberAxis xAxis = new NumberAxis("Sliced Invocations",0,maximum,1);

			if(maximum>=100)
				xAxis.setTickUnit(maximum/20);

			NumberAxis yAxis = new NumberAxis();

			avgPerformanceChart=new LineChart<Number,Number>(xAxis,yAxis);
			avgPerformanceChartPane.getChildren().add(avgPerformanceChart);
			avgPerformanceChart.prefWidthProperty().bind(avgPerformanceChartPane.widthProperty());
			avgPerformanceChart.prefHeightProperty().bind(avgPerformanceChartPane.heightProperty());

			avgPerformanceChart.setLegendVisible(false);
			avgPerformanceChart.getData().clear();

			double maxTime=0;
			double time=0;
			double totalTime=0;
			int count=0;
			int successCount=0;

			series.getData().clear();
			series.getData().add(new Data<Number, Number>(0,time));

	        for(String line:lines){
				String[] str=line.split(",");

				if(str.length>=3){


					if(str[1].equals("AssistanceService")){

						count++;

						if(Boolean.parseBoolean(str[2])){
							successCount++;
							totalTime+=time;
						}

						if(count%slice==0){
							if(totalTime>maxTime)
								maxTime=totalTime;

							series.getData().add(new Data<Number, Number>(count/slice,totalTime/successCount));
							responseTimes.put(count, totalTime/successCount);

							//System.out.println(totalTime/successCount);
							successCount=0;
							totalTime=0;
						}

						time=0;

					}
					else{
						if(Boolean.parseBoolean(str[2])){
							time+=Double.parseDouble(str[5]);
						}
					}
				}
			}

			yAxis.setLabel("Average Responsible Time");
			yAxis.setLowerBound(0);
			//yAxis.setUpperBound(maxTime);
			yAxis.setTickUnit(10);

			avgPerformanceChart.getData().add(series);
		}
		catch(Exception e){
			e.printStackTrace();
		}
	}

	private void generateAvgCostChart(List<String> lines,int maxSteps,int slice){
		try{
			costs=new LinkedHashMap<>();
			costs.put(0, 0.0);

		    avgCostChartPane.getChildren().clear();

			XYChart.Series<Number,Number> costSeries = new XYChart.Series<>();

			int maximum=maxSteps/slice;

			NumberAxis xAxis = new NumberAxis("Sliced Invocations",0,maximum,1);

			if(maximum>=100)
				xAxis.setTickUnit(maximum/20);

			NumberAxis yAxis = new NumberAxis();

			avgCostChart=new LineChart<Number,Number>(xAxis,yAxis);
			avgCostChartPane.getChildren().add(avgCostChart);
			avgCostChart.prefWidthProperty().bind(avgCostChartPane.widthProperty());
			avgCostChart.prefHeightProperty().bind(avgCostChartPane.heightProperty());

			avgCostChart.setLegendVisible(false);
			avgCostChart.getData().clear();

			double maxCost=0;
			double cost=0;
			int count=0;
			//int invocationNum=0;

			costSeries.getData().clear();
			costSeries.getData().add(new Data<Number, Number>(0,cost));

	        for(String line:lines){
				String[] str=line.split(",");
				if(str.length>=3){

					if(str[1].equals("AssistanceService")){

						count++;

						cost+=Double.parseDouble(str[3]);

						if(count%slice==0){
							if(cost>maxCost)
								maxCost=cost;
							costSeries.getData().add(new Data<Number, Number>(count/slice,cost/slice));
							costs.put(count, cost/slice);

							cost=0;
						}

					}
				}
			}

			yAxis.setLabel("Average Cost");
			yAxis.setLowerBound(0);
			yAxis.setUpperBound(maxCost);
			yAxis.setTickUnit(10);

			avgCostChart.getData().add(costSeries);
		}
		catch(Exception e){
			e.printStackTrace();
		}
	}


	private void generateReliabilityChart(List<String> lines,int maxSteps){
		try{

			//reliabilityChartPane.getChildren().clear();

			XYChart.Series<Number,String> reliabilitySeries = new XYChart.Series<>();;

			NumberAxis xAxis = new NumberAxis("Invocations",0,maxSteps,1);

			if(maxSteps>=100)
				xAxis.setTickUnit(maxSteps/20);

	        CategoryAxis yAxis = new CategoryAxis();

	        reliabilityChart=new ScatterChart<Number,String>(xAxis,yAxis);
	        reliabilityChartPane.getChildren().add(reliabilityChart);
	        reliabilityChart.prefWidthProperty().bind(reliabilityChartPane.widthProperty());
	        reliabilityChart.prefHeightProperty().bind(reliabilityChartPane.heightProperty());

	        reliabilityChart.setLegendVisible(false);

			int invocationNum=0;
			int minVocationNum=Integer.MAX_VALUE;
			String service;
			boolean result;

	        List<String> categories=new ArrayList<>();
			categories.add("AssistanceService");
			for(String line:lines){
				String[] str=line.split(",");
				if(str.length>=3){
					invocationNum=Integer.parseInt(str[0]);
					if(minVocationNum>invocationNum)
						minVocationNum=invocationNum;
					service=str[1];
					result=Boolean.parseBoolean(str[2]);
					//if(!service.equals("AssistanceService")){
						reliabilitySeries.getData().add(this.createReliabilityData(invocationNum, service, result,maxSteps));
						if(!categories.contains(service) && !service.equals("AssistanceService"))
							categories.add(service);
					//}
				}
			}


			//NumberAxis xAxis = new NumberAxis("Invocation",minVocationNum,invocationNum,1);
			//xAxis.setLabel("Invocation");
			//xAxis.setLowerBound(1);
			//xAxis.setUpperBound(invocationNum);
			//xAxis.setTickUnit(1);
			//xAxis.setAutoRanging(true);
	        //xAxis.setMinorTickCount(1);

	        //CategoryAxis yAxis = new CategoryAxis();
	        yAxis.setAutoRanging(false);
	        yAxis.setCategories(FXCollections.<String>observableArrayList(categories));
	        yAxis.invalidateRange(categories);

	        reliabilityChart.getData().add(reliabilitySeries);

		}
		catch(Exception e){
			e.printStackTrace();
		}
	}


	private void generateInvCostChart(List<String> lines,int maxSteps){
		try{

			XYChart.Series<Number,Number> costSeries = new XYChart.Series<>();;

			NumberAxis xAxis = new NumberAxis("Invocations",0,maxSteps,1);
			if(maxSteps>=100)
				xAxis.setTickUnit(maxSteps/20);

			NumberAxis yAxis = new NumberAxis();

			invCostChart=new LineChart<Number,Number>(xAxis,yAxis);
			invCostChartPane.getChildren().add(invCostChart);
			invCostChart.prefWidthProperty().bind(invCostChartPane.widthProperty());
			invCostChart.prefHeightProperty().bind(invCostChartPane.heightProperty());

			invCostChart.setLegendVisible(false);
			invCostChart.getData().clear();

			double maxCost=0;
			double cost=0;
			int invocationNum=0;
			int minVocationNum=Integer.MAX_VALUE;
			String service;

			costSeries.getData().clear();

			costSeries.getData().add(new Data<Number, Number>(0,cost));

	        for(String line:lines){
				String[] str=line.split(",");
				if(str.length>=3){
					invocationNum=Integer.parseInt(str[0]);
					if(minVocationNum>invocationNum)
						minVocationNum=invocationNum;
					service=str[1];

					if(service.equals("AssistanceService")){
						cost=Double.parseDouble(str[3]);
						if(cost>maxCost)
							maxCost=cost;
						costSeries.getData().add(new Data<Number, Number>(invocationNum,cost));
					}
				}
			}

			yAxis.setLabel("Invocation Cost");
			yAxis.setLowerBound(0);
			yAxis.setUpperBound(maxCost);
			yAxis.setTickUnit(10);

			invCostChart.getData().add(costSeries);
		}
		catch(Exception e){
			e.printStackTrace();
		}
	}

	private void generateCostChart(List<String> lines,int maxSteps){

		try{
			//costChartPane.getChildren().clear();

			XYChart.Series<Number,Number> costSeries = new XYChart.Series<>();;


			NumberAxis xAxis = new NumberAxis("Invocations",0,maxSteps,1);
			if(maxSteps>=100)
				xAxis.setTickUnit(maxSteps/20);

			NumberAxis yAxis = new NumberAxis();

	        costChart=new LineChart<Number,Number>(xAxis,yAxis);
	        costChartPane.getChildren().add(costChart);
	        costChart.prefWidthProperty().bind(costChartPane.widthProperty());
	        costChart.prefHeightProperty().bind(costChartPane.heightProperty());

	        costChart.setLegendVisible(false);
	        costChart.getData().clear();

			double totalCost=0;
			int invocationNum=0;
			int minVocationNum=Integer.MAX_VALUE;
			String service;

			costSeries.getData().clear();

			costSeries.getData().add(new Data<Number, Number>(0,totalCost));

	        for(String line:lines){
				String[] str=line.split(",");
				if(str.length>=3){
					//System.out.println(str[0]);
					invocationNum=Integer.parseInt("+"+str[0]);
					if(minVocationNum>invocationNum)
						minVocationNum=invocationNum;
					service=str[1];

					if(service.equals("AssistanceService")){
						totalCost=totalCost+Double.parseDouble(str[3]);
						costSeries.getData().add(new Data<Number, Number>(invocationNum,totalCost));
					}
				}
			}

			//NumberAxis xAxis = new NumberAxis("Invocation",minVocationNum,invocationNum,1);
			//xAxis.setLabel("Invocation");
			//xAxis.setLowerBound(minVocationNum);
			//xAxis.setUpperBound(invocationNum);
			//xAxis.setTickUnit(1);
	        //xAxis.setMinorTickCount(0);

	        //NumberAxis yAxis = new NumberAxis("Cost",0,totalCost,100);
			yAxis.setLabel("Cost");
			yAxis.setLowerBound(0);
			yAxis.setUpperBound(totalCost);
			yAxis.setTickUnit(100);

	        //yAxis.setMinorTickCount(0);
	        costChart.getData().add(costSeries);
		}
		catch(Exception e){
			e.printStackTrace();
		}
	}

	private void generatePerformanceChart(List<String> lines, int maxSteps){
		try{

			CategoryAxis xAxis = new CategoryAxis();
			xAxis.setLabel("Invocations");

			NumberAxis yAxis = new NumberAxis();
			yAxis.setLabel("Response Time / ms ");

	        performanceChart=new StackedBarChart<String,Number>(xAxis,yAxis);
	        performanceChartPane.getChildren().add(performanceChart);
	        performanceChart.prefWidthProperty().bind(performanceChartPane.widthProperty());
	        performanceChart.prefHeightProperty().bind(performanceChartPane.heightProperty());

	        //performanceChart.setLegendVisible(false);

			String invocationNum;
			String service;
			String invisible=new String();
			int tickUnit=maxSteps/20;
			//boolean result;

	        //List<String> categories=new ArrayList<>();
			//categories.add("AssistanceService");
			Map<String,XYChart.Series<String,Number>> delays=new LinkedHashMap<>();
	        //List<String> categories=new ArrayList<>();

			for(String line:lines){
				String[] str=line.split(",");

				if(str.length==6){

					if(maxSteps>=100 && (Integer.parseInt(str[0])%tickUnit!=0) && (Integer.parseInt(str[0])!=maxSteps)){
						invisible+=(char)29;
						invocationNum=invisible;
					}
					else
						invocationNum=str[0];

					//System.out.println(invocationNum);

					service=str[1];
					//result=Boolean.parseBoolean(str[2]);

					if(!service.equals("AssistanceService")){
						Double delay=Double.parseDouble(str[5]);

						if(!delays.containsKey(service)){
							XYChart.Series<String,Number> delaySeries=new XYChart.Series<>();
							delaySeries.setName(service);
							delays.put(service, delaySeries);
						}
						XYChart.Series<String,Number> delaySeries=delays.get(service);

						delaySeries.getData().add(new XYChart.Data<String,Number>(invocationNum,delay));
					}
				}
			}

			performanceChart.setCategoryGap(performanceChart.widthProperty().divide(maxSteps*5).get());

	        List<String> categories=new ArrayList<>();
	        invisible=new String();
	        	for(int i=1;i<=maxSteps;i++){
	        		if(maxSteps>=100 && i%tickUnit!=0 && (i!=maxSteps)){
						invisible+=(char)29;
		        		categories.add(invisible);
	        		}
	        		else{
		        		categories.add(String.valueOf(i));
		        		//System.out.println(i);
	        		}
	        	}

	        xAxis.setCategories(FXCollections.<String>observableArrayList(categories));
	        performanceChart.getData().addAll(delays.values());
		}
		catch(Exception e){
			e.printStackTrace();
		}
	}


	public void clear(){
	    reliabilityChartPane.getChildren().clear();
	    costChartPane.getChildren().clear();
	    performanceChartPane.getChildren().clear();
	    invCostChartPane.getChildren().clear();
	}

	public Data<Number, String> createReliabilityData(int num,String service,boolean result,int maxSteps){
        Data<Number, String> data=  new Data<Number, String>(num, service);
        if(result){

            Rectangle rect = new Rectangle();
            rect.setHeight(20);
            //rect.setWidth(5);
            rect.widthProperty().bind(reliabilityChart.widthProperty().divide(maxSteps).divide(3));
            rect.setFill(Color.LIMEGREEN);
            data.setNode(rect);
            data.setNode(rect);
        }
        else{
            Rectangle rect = new Rectangle();
            rect.setHeight(40);
            //rect.setWidth(5);
            rect.widthProperty().bind(reliabilityChart.widthProperty().divide(maxSteps).divide(2));
            rect.setFill(Color.RED);
            data.setNode(rect);
            data.setNode(rect);
        }
        return data;
	}
}
