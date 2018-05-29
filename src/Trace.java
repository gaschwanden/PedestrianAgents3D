import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;


public class Trace {
	PApplet p;
	Vector<PVector> pos;
	int age;
	Agent agent;
	int maxAge = 800;
	int startFrame;
	int start_od;
	int end_od;
	boolean active;
	int colRed 		= 0;
	int colGreen 	= 50;
	int colBlue 	= 200;
	boolean drawMe = true;

	
	public Trace(PApplet _p, Agent _agent, boolean draw) {
		p				=_p;
		agent			=_agent;
		agent.trace 	= this;
		startFrame 		= p.frameCount;
		pos 			= new Vector<PVector>();
		age 			= 0;
		start_od 		= agent.origin;
		end_od 			= agent.target;
		active 			= true;
		drawMe = draw;
	}

	public void draw(boolean OColour, Scene scene) {

		//if (!active) return;
		if ( pos.size() < Scene.TRACERESO )         return;
		    
		p.noFill();
		    
		PVector a,b,c;
		    
		//translate
		float trans = 0; 

		if      (Scene.DO_AGEING_TRACES)                     trans -= ((float)age)/100.0;

		//p.strokeWeight(3); // // 
		//if (!active) p.strokeWeight(p.max(1,p.map(age,0,maxAge,1,4)));
		           
		setStrokeColour(OColour, scene);
		p.pushMatrix();
			p.translate(0,0,trans);
		    
		    if (Scene.SMOOTHTRACE) {
		    	p.beginShape();
		    	a = (PVector)pos.elementAt(1);
		    	p.vertex(a.x, a.y, a.z);
		    	for (int i = Scene.TRACERESO; i < pos.size()-1; i+= Scene.TRACERESO) {  
		    		a = pos.elementAt(i-( Scene.TRACERESO/3*2));
		    		b = pos.elementAt(i-( Scene.TRACERESO/3));
		    		c = pos.elementAt(i);

		    		p.bezierVertex(a.x, a.y,a.z, b.x,b.y,b.z, c.x, c.y, c.z);
		    	}
		      
		    	int rest = (pos.size()-2)% Scene.TRACERESO;
		    	a = (PVector)pos.elementAt(pos.size()-1-(rest/3*2));
		    	b = (PVector)pos.elementAt(pos.size()-1-(rest/3));
		    	c = (PVector)pos.elementAt(pos.size()-1);
		    	p.bezierVertex(a.x, a.y, a.z, b.x,b.y, b.z, c.x, c.y, c.z);
		    	p.endShape();
		    }
		    else { //not smooth
		    	p.beginShape();
		    	a = (PVector)pos.elementAt(1);
		    	p.vertex(a.x, a.y, a.z);
		    	for (int i = 1; i < pos.size()-1; i+=Scene.TRACERESOSTRAIGHT) {  
		    		c = (PVector)pos.elementAt(i);
		    		p.vertex(c.x, c.y, c.z);
		    	}
		    	p.endShape();
		    }
		p.popMatrix();
		p.strokeWeight(1);
	}
	

	
	private void setStrokeColour(boolean OColour, Scene scene) {
		if (!OColour) 	// standard draw
		  p.stroke(colRed * (maxAge-age) / maxAge,
				  colGreen* (maxAge-age) / maxAge,
				  colBlue * (maxAge-age) / maxAge); 
		else { 			// rgb draw
			//if (this.start_od == 0) {
			try {
			if (scene.ods[start_od].group == 0) {
				 p.stroke(255 * (maxAge-age) / maxAge,
						  0   * (maxAge-age) / maxAge,
						  0   * (maxAge-age) / maxAge);
			}
			//else if (this.start_od == 1) {
			else if (scene.ods[start_od].group == 1) {
				p.stroke( 0   * (maxAge-age) / maxAge,
						  255 * (maxAge-age) / maxAge,
						  0   * (maxAge-age) / maxAge);
				
			}
			//else if (this.start_od == 2) {
			else if (scene.ods[start_od].group == 2) {
				p.stroke( 0   * (maxAge-age) / maxAge,
						  0   * (maxAge-age) / maxAge,
						  255 * (maxAge-age) / maxAge);
				
			}
			else  {
				p.stroke( 150   * (maxAge-age) / maxAge,
						  150  * (maxAge-age) / maxAge,
						  150 * (maxAge-age) / maxAge);
				
			}
			}
			catch (NullPointerException e) {
				p.stroke(colRed * (maxAge-age) / maxAge,
						  colGreen* (maxAge-age) / maxAge,
						  colBlue * (maxAge-age) / maxAge);
			}
		}
	}
	
	public void update(Scene scene)
	{
		if (active) {
			addPos(agent.px*agent.gridsize+agent.sx,agent.py*agent.gridsize+agent.sy, 0); //add pos
		}
		//else {
			// age
			age++;
		//}
		// delete?
		if (age > maxAge) {
			scene.traces.remove(this);
		}
	}
	

	
	
	void addPos(float x, float y, float z) 
	{
	    PVector p = new PVector(x,y,z);
	    pos.addElement(p);
	    //calculate angle change
	    if (pos.size() > 2) {
	      PVector a = new PVector();
	      PVector b = new PVector();
	      a.set((PVector)pos.elementAt(pos.size()-2));
	      b.set((PVector)pos.elementAt(pos.size()-1));
	      a.sub((PVector)pos.elementAt(pos.size()-3));
	      b.sub((PVector)pos.elementAt(pos.size()-2));
	        
	    }
	}

}
