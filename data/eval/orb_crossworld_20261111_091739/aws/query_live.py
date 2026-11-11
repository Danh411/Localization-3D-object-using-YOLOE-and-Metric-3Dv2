import math
import json
import rclpy
from rclpy.node import Node
from scan_interfaces.srv import QueryObjects, GetApproachPoint

rclpy.init()
node = Node('fullscan_query_audit')
def call(client, request):
    assert client.wait_for_service(timeout_sec=8)
    future = client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=8)
    assert future.done()
    return future.result()

try:
    query = node.create_client(QueryObjects,'/db/query')
    approach = node.create_client(GetApproachPoint,'/db/approach_point')
    response = call(query,QueryObjects.Request(class_name='',max_range_m=0.,min_observations=1))
    rows = []
    for key,cls,x,y in zip(response.object_id,response.class_name,response.x,response.y,strict=True):
        p = call(approach,GetApproachPoint.Request(object_id=key,standoff_m=.6))
        assert p.success
        origin = (-2.0, 0.75)
        expected = min(.6,math.dist((x,y),origin))
        distance = math.dist((x,y),(p.x,p.y))
        assert math.isclose(distance,expected,abs_tol=1e-8)
        assert math.isclose(math.dist(origin,(p.x,p.y))+distance,math.dist(origin,(x,y)),abs_tol=1e-8)
        assert math.isclose(math.cos(p.yaw_rad-math.atan2(y-p.y,x-p.x)),1.,abs_tol=1e-8)
        rows.append(dict(object_id=key,class_name=cls,x=x,y=y,approach_x=p.x,approach_y=p.y,
                         yaw=p.yaw_rad,distance_to_db_object=distance,already_close=p.already_close))
    assert not call(query,QueryObjects.Request(class_name='_missing_',max_range_m=0.,min_observations=1)).object_id
    assert not call(approach,GetApproachPoint.Request(object_id=-1,standoff_m=.6)).success
    print(json.dumps(rows,indent=2))
finally:
    node.destroy_node()
    rclpy.shutdown()
