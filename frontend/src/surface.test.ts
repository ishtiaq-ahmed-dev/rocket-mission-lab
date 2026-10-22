import {describe,it,expect} from 'vitest';
import {terrainSites,sceneSurfaceHeight} from './surface';
import {terrainHeight} from './terrain';
describe('relocated coastal sites',()=>{
  const plan={launch:[-500,700] as [number,number],landing:[200,-350] as [number,number],separation_altitude:400};
  for(const mode of ['Coastal','Ship'])it(`keeps both sites flat at the physics contact plane in ${mode}`,()=>{
    for(const [x,y] of [plan.launch,plan.landing]){
      expect(sceneSurfaceHeight(x,-y,plan,mode)).toBeCloseTo(0);
      expect(sceneSurfaceHeight(x+20,-y,plan,mode)).toBeCloseTo(0);
    }
    expect(terrainSites(plan,mode)[0][1]).toBe(-700);
  });
  it('preserves the original landscape away from site earthworks',()=>{
    const sites=terrainSites(plan,'Coastal');
    for(const [x,z] of [[-900,1000],[350,50],[0,0]])expect(terrainHeight(x,z,sites)).toBe(terrainHeight(x,z));
  });
  it('does not raise an island through the offshore ship deck',()=>{
    const sites=terrainSites(plan,'Ship');
    expect(sites).toHaveLength(1);
    expect(sites[0]).toEqual([350,-700]);
  });
});
