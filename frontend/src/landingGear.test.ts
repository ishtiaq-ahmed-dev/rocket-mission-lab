import {describe,it,expect} from 'vitest';
import {gearDeployment,legFoot,LEG_HINGE,LEG_LENGTH} from './gearKinematics';
import {NOZZLE_EXIT_Y,CONTACT_Y} from './vehicleDimensions';
describe('hinged landing supports',()=>{
  it('places deployed foot soles on the 40 m vehicle contact plane',()=>{
    const foot=legFoot(1);
    expect(foot[0]).toBeCloseTo(6.2);
    expect(foot[1]-.15).toBeCloseTo(CONTACT_Y);
    expect(NOZZLE_EXIT_Y-CONTACT_Y).toBeCloseTo(.6);
    expect(foot[0]).toBeGreaterThan(1.8+.82);
  });
  it('folds up alongside the body without shrinking the load-carrying arm',()=>{
    for(const amount of [0,.1,.5,.9,1]){
      const foot=legFoot(amount);
      expect(Math.hypot(...foot.map((v,i)=>v-LEG_HINGE[i]))).toBeCloseTo(LEG_LENGTH);
      expect(foot[0]-.82).toBeGreaterThan(0);
    }
    expect(legFoot(0)[1]).toBeGreaterThan(-13);
    expect(legFoot(0)[0]).toBeLessThan(2.1);
  });
  it('stows on launch supports and deploys before final landing',()=>{
    expect(gearDeployment('takeoff',0)).toBe(0);
    expect(gearDeployment('takeoff',20)).toBe(0);
    expect(gearDeployment('landing',100)).toBe(0);
    expect(gearDeployment('landing',35)).toBe(1);
    expect(gearDeployment('landing',-1)).toBe(1);
    const sequence=[100,90,75,60,40,35].map(h=>gearDeployment('landing',h));
    expect(sequence).toEqual([...sequence].sort((a,b)=>a-b));
  });
});
