import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;


public class Agent {
	static final int died_targetReached = 0;
	static final int died_targetGone 	= 1;
	static final int died_lost 			= 2;
	PApplet p;
	int target;
	int origin;
	float far_px; float far_py; 
	float px,py,pz,vx,vy, speed = 0.5f;
	boolean active;
	int age;
	
	float gridsize;
	float sx,sy;

	float mSize = 2;
	
	Scene scene;
	public Trace trace;
	int precentTracesToDraw = 10;  // drawing x percent traces
	
	public Agent(PApplet _p, float gsize, float _sx, float _sy, Scene _scene)
	{
		p=_p;
		gridsize = gsize;
		scene = _scene;
		sx=_sx;
		sy=_sy;
		pz = 2;
		active = false;
		far_px=-1; far_py=-1; 
		
	}
	
	public void draw()
	{
		//p.println(active);
		if (!active) return;
			
		//p.println("katz");
		p.noStroke();
		p.fill(255,150,0);
		if (scene.analysis_mode == Scene.display_facadevisibilityO
				|| scene.analysis_mode == Scene.display_tracesO) {
			/*if (origin == 0) p.fill(255,0,0);
			else if (origin == 1) p.fill(0,255,0);
			else if (origin == 2) p.fill(0,0,255);*/
			if (scene.ods[origin].group == 0) p.fill(255,0,0);
			else if (scene.ods[origin].group == 1) p.fill(0,255,0);
			else if (scene.ods[origin].group == 2) p.fill(0,0,255);
		}
		
		
		
		p.pushMatrix();
			p.translate(px*gridsize+sx,py*gridsize+sy,pz);
			p.ellipseMode(p.CENTER);
			p.ellipse(0,0, mSize,mSize);
		p.popMatrix();
		//p.stroke(255);
		//p.line(px*gridsize+sx,py*gridsize+sy,pz,far_px*gridsize+sx,far_py*gridsize+sy,pz);
		age++;
	}
	
	public void die(int reason) {
		//p.println(reason);
		if (trace!=null && reason == died_targetReached) {
			// give the trace the last coordinate, otherwise looks funny
			
			if (target<scene.ods.length&& target>-1) {
				if (scene.ods[target]!=null) {
					trace.addPos(scene.ods[target].pos.x,scene.ods[target].pos.y,scene.ods[target].pos.z);
				}
			}
		}
		active = false;
		far_px=-1; far_py=-1; 
		target=-1;
		origin=-1;
		
		age=0;
		
	}

	public void setDirToTarget() {
		int t = target;
	    int xxx; int yyy;
	    
	    vx=0; vy=0;

	    //if (scene.ods.size()>0) { // // // // 
	    	PVector dir = new PVector();
	        //vector field from the obstacles!!   
	        xxx = (int)(px); if (xxx<0) xxx = 0; else if(xxx>=scene.grid.gridPoints.length)    xxx = scene.grid.gridPoints.length    -1;
	        yyy = (int)(py); if (yyy<0) yyy = 0; else if(yyy>=scene.grid.gridPoints[0].length) yyy = scene.grid.gridPoints[0].length -1;   
	               
	            
	        //read the destination pixel that goes to the target
	        if (far_px != -1 && far_py != -1) {
	                dir.x = far_px;
	                dir.y = far_py;
	                dir.x-= px;
	                dir.y-= py;
	                dir.normalize();
	                vx += dir.x;
	                vy += dir.y;
	        }
	        //end read the destination pixel that goes to the target
	            
	          
	        // fix .... agents that move nowhere
	        if (dir.mag() == 0) { 
	              //
	              //check the 8 fields around me and see if any of these are closer to my target
	              //we need to do this step otherwise too many agents die.
	              // maybe we can skip the vector field checking step instead, so city map calculations could be quicker....
	              //
	              
	              //println("ckecking distances in citymap...");
	              float minD = 99999999; int mx=-1; int my=-1;
	              //boolean found = false;  // don't stop when found...agents tend to get stuck!
	                                        // we need to figure out somethign else so they dont walk through the walls.....
	              
	              
	              for (int depth = 1; depth < 4 /*&& found==false*/; depth++){
	            	  for (int kk = 0-depth; kk < 1+depth; kk++) {
	            		  xxx = (int)px+kk; if (xxx<0) continue; if (xxx>=scene.grid.gridPoints.length) continue;
	            		  for (int kkk = 0-depth; kkk < 1+depth; kkk++) {
	            			  if (kk==0 && kkk==0) continue;
	            			  yyy = (int)py+kkk; if (yyy<0) continue; if (yyy>=scene.grid.gridPoints[0].length) continue;
	  
	            			  //if (cityMap.distance[target[i]][xxx][yyy] < minD && cityMap.distance[target[i]][xxx][yyy] > 0) //if this is closer to the target, but greater than 0 (not initialised)
	            			  //p.println(scene.grid.gridPoints[xxx][yyy].dist[target] +" "+
	            					  //(scene.grid.gridPoints[xxx][yyy].dist[target] < minD));
	            			  if (scene.grid.gridPoints[xxx][yyy].dist[target] < minD && scene.grid.gridPoints[xxx][yyy].dist[target] > 0)
	            			  { 
	            				  //minD=cityMap.distance[target[i]][xxx][yyy]; 
	            				  minD = scene.grid.gridPoints[xxx][yyy].dist[target]; 
	            				  mx=xxx;my=yyy; 
	            				  //break;
	            			  }
	            		  }
	            	  }
	              }
	              if (mx!=-1) {
	            	  	dir.x = mx;
	            	  	dir.y = my;
	            	  	dir.x-= px;
	            	  	dir.y-= py;
	                	dir.normalize();
	                	vx += dir.x;
	                	vy += dir.y;
	                	//far_px = mx;
	                	//far_py = my;
	              }
	              else {  //no closest pixel seen, give up.....
	            	  //p.println(" died"); 
	            	  die(died_lost);
	              }
	          } // end fix
	     }   // end targets.size
	//}

	public void move() {
		PVector vvv = new PVector(vx, vy);   
	    vvv.normalize();

	    vvv.mult(speed);     // // // 
	    //gate count
	    //if (do_gate_counts) { gate_count(px[i]*gridSize,py[i]*gridSize,( px[i] + vvv.x)*gridSize, (py[i] + vvv.y)*gridSize); }
	    //move
	    px += vvv.x;  //this is the normal  walking speed
	    py += vvv.y; 
	    //p.println(vvv);
	    
	    
	    //safety check
	    if (px<0) px=0;
	    if (px>scene.grid.gridPoints.length-1) px=scene.grid.gridPoints.length-1;
	    if (py<0) py=0;
	    if (py>scene.grid.gridPoints[0].length-1) py=scene.grid.gridPoints[0].length-1;
	          
	    //pz[i] = getZLevel(px[i], py[i], i==0);
		
	}

	public void markOccupancy() {
		int mm = 2;
		if (age < mm) return;
		
		int xxx = (int)(px); if (xxx<0) xxx = 0; else if(xxx>=scene.grid.gridPoints.length)    xxx = scene.grid.gridPoints.length    -1;
        int yyy = (int)(py); if (yyy<0) yyy = 0; else if(yyy>=scene.grid.gridPoints[0].length) yyy = scene.grid.gridPoints[0].length -1; 
        if (scene.grid.gridPoints[xxx][yyy].dist[target] < mm) return;
        
        if (!scene.grid.gridPoints[xxx][yyy].walkable()) return;
	      
	    //mark occupancy map - only when entering a new pix
	    //if ((int)px[i] == lastx && (int)py[i] == lasty) {}
	    //else   
	    int xx = (int)px;int yy = (int)py;
	    scene.grid.gridPoints[xx][yy].occupancy ++;
	          
	    //blur!
	    if (scene.blur_pathoverlap) {
	            
	            if (xx>0 && xx<scene.grid.gridPoints.length-1 && yy>0 && yy<scene.grid.gridPoints[0].length-1) {
	              float rex = px-xx;float rey = py-yy;
	              scene.grid.gridPoints[xx-1][yy+1].occupancy += (1.0-rex)/2.0*scene.blurdecay;
	              scene.grid.gridPoints[xx-1][yy].occupancy   += (1.0-rex)    *scene.blurdecay;
	              scene.grid.gridPoints[xx-1][yy-1].occupancy += (1.0-rex)/2.0*scene.blurdecay;
	              
	              scene.grid.gridPoints[xx+1][yy+1].occupancy += (rex)/2.0    *scene.blurdecay;
	              scene.grid.gridPoints[xx+1][yy].occupancy   += (rex)        *scene.blurdecay;
	              scene.grid.gridPoints[xx+1][yy-1].occupancy += (rex)/2.0    *scene.blurdecay;
	              
	              scene.grid.gridPoints[xx-1][yy-1].occupancy += (1.0-rex)/2.0*scene.blurdecay;
	              scene.grid.gridPoints[xx  ][yy-1].occupancy += (1.0-rex)    *scene.blurdecay;
	              scene.grid.gridPoints[xx+1][yy-1].occupancy += (1.0-rex)/2.0*scene.blurdecay;
	              
	              scene.grid.gridPoints[xx-1][yy+1].occupancy += (1.0-rex)/2.0*scene.blurdecay;
	              scene.grid.gridPoints[xx  ][yy+1].occupancy += (1.0-rex)    *scene.blurdecay;
	              scene.grid.gridPoints[xx+1][yy+1].occupancy += (1.0-rex)/2.0*scene.blurdecay;
	        }
	    }
		
	}

	public void TargetCheck() {
		if (target<0||target>=scene.ods.length) {
			die(died_targetGone);
	    	renew();
            return;
		}
		if (scene.ods[target] == null) {
            //my target is gone!!
            //renewTarget();
			die(died_targetGone);
	    	renew();
            return;
        }
        OD od = scene.ods[target];
        int odpx = scene.grid.getGridcellX(od.pos.x);
        int odpy = scene.grid.getGridcellY(od.pos.y);
        

       if ( PApplet.abs(px-odpx) < 3  &&
    		PApplet.abs(py-odpy) < 3 )
       {
    	   //p.println("arrive");
    	   die(died_targetReached);
    	   renew();
    	   return;
       }       
		
	}

	public void renew() {
		Vector <OD> actualODs = new Vector<OD>();
		Vector<Float> weightsO = new Vector<Float>();
		Vector<Float> weightsD = new Vector<Float>();
		for (int i = 0; i < scene.ods.length; i++) {
			if (scene.ods[i]!=null) {
				actualODs.addElement(scene.ods[i]);
				weightsO.addElement(new Float(scene.ods[i].oWeight));
				weightsD.addElement(new Float(scene.ods[i].dWeight));
			}
		}
		if (actualODs.size()<2) return;
		
		
		int oo = scene.myMath.WeightedDrawf(weightsO);
		if (oo == -1) return;

		int dd = scene.myMath.WeightedDrawf(weightsD,oo);

		// actual indices:
		int num = 0;
		int o=-1; int d=-1;
		for (int i = 0; i < scene.ods.length; i++) {
			if (scene.ods[i]!=null) {
				if (num==oo) o=i;
				if (num==dd) d=i;
				num++;
			}
		}

		
		if (o==-1||d==-1) return; // security
		
		
		////////////////////////////////
		//set origin 
		////////////////////////////////
		origin 	= o;
		px 		= (scene.ods[o].pos.x-scene.grid.sx) / scene.grid.gridsize;
		py 		= (scene.ods[o].pos.y-scene.grid.sy) / scene.grid.gridsize;
		target = d;

		vx = 0;
		vy = 0;
		
		//traces
		for (int i = 0; i < scene.traces.size(); i++) {
					if (scene.traces.elementAt(i).agent.equals(this))
						scene.traces.elementAt(i).active=false;
		}
		trace = null;
		scene.traces.addElement(new Trace(p, this, (Math.random()*100 <precentTracesToDraw)));  // draw roughly every third trace only
		scene.traces.lastElement().update(scene);		
		active = true;
	
	}

}
