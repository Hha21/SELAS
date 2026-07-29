package tas.services.log;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.RandomAccessFile;
import java.nio.channels.FileLock;
import java.text.SimpleDateFormat;
import java.util.Date;

import javafx.collections.FXCollections;
import javafx.collections.ObservableList;

public class Log {
	// Unbounded logData caused long runs (e.g. 10,000-step profiles) to grow memory/JavaFX
	// list-change overhead without limit, and re-reading the whole persisted log file on every
	// startup compounded it across sessions. Cap it; the on-disk file (out.println below) still
	// keeps the full history, only the in-memory/GUI-visible list is bounded.
	private static final int MAX_ENTRIES = 2000;
	public static ObservableList<LogEntry> logData = FXCollections.observableArrayList();
	private static PrintWriter out;
	private static String logFile;

	private static void addEntry(LogEntry entry){
		logData.add(entry);
		if (logData.size() > MAX_ENTRIES) {
			logData.remove(0);
		}
	}
	
	public static void initialize(String file){
		try {
			logFile=file;
			out = new PrintWriter(new BufferedWriter(new FileWriter(logFile, true)));
			readFromFile(logFile);
		} catch (IOException e) {
			e.printStackTrace();
		}
	}

	public static void stop(){
		out.close();
	}
	
	public static void addLog(String title,String message){
		SimpleDateFormat dataFormat = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
        Date date = new Date();  
        String time=dataFormat.format(date).toString();

		addEntry(new LogEntry(time,title,message));
		out.println(time+","+title+","+message);
	}
	
	public static void clear(){
		try{
			//FileOutputStream fos = new FileOutputStream(logFile);
			//FileLock lock=fos.getChannel().tryLock();
			
			File file = new File(logFile);
			FileLock lock = new RandomAccessFile(file, "rw").getChannel().lock();

			if(lock!=null){
				System.out.println("file locked");
				file.delete();
				file.createNewFile();
				lock.release();
				System.out.println("file released");
				logData.clear();
			}
			
		}
		catch(Exception e){
			e.printStackTrace();
		}
	}
	
	/*
	public static void saveToFile(String logFile){
		try {			
			PrintWriter out = new PrintWriter(new BufferedWriter(new FileWriter(logFile, true)));
			for(LogEntry entry:logData){
				out.println(entry.getTime()+","+entry.getTitle()+","+entry.getMessage());
			}
			out.close();
			
		} catch (IOException e) {
			e.printStackTrace();
		}
		System.out.println("save to file "+logFile);
	}*/
	
	private static void readFromFile(String logFile){
		try{
			File file = new File(logFile);
			if(!file.exists()) {
				file.createNewFile();
			} 
			
			BufferedReader br = new BufferedReader(new FileReader(logFile));
			String line;
	        while ((line = br.readLine()) != null) {
				String[] strs=line.split(",");
				if(strs.length==3){
					addEntry(new LogEntry(strs[0],strs[1],strs[2]));
				}
			}
			br.close();
		}
		catch(Exception e){
			e.printStackTrace();
		}
		System.out.println("read from file "+logFile);
	}
	
}
