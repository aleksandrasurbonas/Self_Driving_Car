import pymunk
from pymunk import Vec2d
from math import pi

from utils import add_debug_point

import torch


def body_col_begin(arbiter, space, data):
    data["Collision_Function"]()
    return True


class Car:
    def __init__(self, space, x, y, body_no, environment):
        # Space
        self.space = space
        self.environment = environment
        # Car Properties
        self.init_position = x, y
        self.init_angle = 0
        self.car_size = 10
        self.car_dimension = 40, 20
        self.car_color = 0, 255, 0
        self.car_elasticity = 0
        # Car sensors
        self.sensors = []
        self.sensor_distance = [10 for _ in range(5)]
        self.sensor_angles = [0, pi / 6, -pi / 6, pi / 3, -pi / 3]
        # Collision properties
        self.body_collision_type = body_no
        self.sensor_collision_type = [3, 4, 5, 6, 7]
        self.car_collided = False

        # Create
        self.create()
        for distance, angle, collision_type in zip(
            self.sensor_distance,
            self.sensor_angles,
            self.sensor_collision_type
        ):
            self.create_sensor(distance, angle, collision_type)
        self.create_nose()
        self.add_body_collision_handler()
        self.sensor_collision_handler()

        # Driver
        self.driver = None

    def create(self):
        inertia = pymunk.moment_for_box(self.car_size, self.car_dimension)
        self.car_body = pymunk.Body(
            self.car_size, inertia, body_type=pymunk.Body.KINEMATIC)
        self.car_body.position = self.init_position
        self.car_shape = pymunk.Poly.create_box(
            self.car_body,
            self.car_dimension)
        self.car_shape.collision_type = self.body_collision_type
        self.car_shape.color = self.car_color
        self.car_shape.elasticity = self.car_elasticity
        self.car_body.angle = self.init_angle
        driving_direction = Vec2d(1, 0).rotated(self.car_body.angle)
        self.car_body.apply_impulse_at_local_point(driving_direction)
        self.space.add(self.car_body, self.car_shape)

    def move(self, force, max_force=5):
        driving_direction = Vec2d(1, 0).rotated(self.car_body.angle)
        self.car_body.position += min(force, max_force) * driving_direction
        self.sensor_update()
        self.nose_update()

    def rotate(self, angle, max_angle=pi / 36):
        self.car_body.angle += min(angle, max_angle)
        self.sensor_update()
        self.nose_update()

    def get_vertices(self):
        vertices = []
        for v in self.car_shape.get_vertices():
            vertex = v.rotated(self.car_body.angle) + self.car_body.position
            vertices.append(vertex)
        return vertices

    def create_sensor(self, distance, angle, collision_type):
        sensor_direction = Vec2d(1, 0).rotated(self.car_body.angle + angle)
        sensor_body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        vertex = self.get_vertices()
        sensor_body.position = (vertex[1] + vertex[0]) / 2
        sensor_start = (0, 0)
        sensor_end = distance * sensor_direction
        sensor_shape = pymunk.Segment(sensor_body, sensor_start, sensor_end, 1)
        sensor_shape.collision_type = collision_type
        self.space.add(sensor_body, sensor_shape)
        self.sensors.append([sensor_body, sensor_shape])

    def sensor_update(self):
        self.sensor_collision_handler()
        for i in range(len(self.sensors)):
            vertex = self.get_vertices()
            self.sensors[i][0].position = (vertex[1] + vertex[0]) / 2
            sensor_direction = Vec2d(1, 0).rotated(
                self.car_body.angle + self.sensor_angles[i])
            self.sensors[i][1].unsafe_set_endpoints(
                (0, 0), self.sensor_distance[i] * sensor_direction)

    def create_nose(self):
        self.nose_body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        vertex = self.get_vertices()
        offset = Vec2d(5, 0).rotated(self.car_body.angle)
        self.nose_body.position = (vertex[1] + vertex[0]) / 2 - offset
        self.nose_shape = pymunk.Circle(self.nose_body, 5)
        self.nose_shape.collision_type = self.body_collision_type
        self.nose_shape.color = (0, 0, 255)
        self.space.add(self.nose_shape, self.nose_body)

    def nose_update(self):
        vertex = self.get_vertices()
        offset = Vec2d(5, 0).rotated(self.car_body.angle)
        self.nose_body.position = (vertex[1] + vertex[0]) / 2 - offset

    def add_body_collision_handler(self):
        self.body_handler = self.space.add_collision_handler(
            1, self.body_collision_type)
        self.body_handler.data["Collision_Function"] = self.set_car_collision
        self.body_handler.begin = body_col_begin

    def sensor_collision_handler(self):
        for i, sensor in enumerate(self.sensors):
            if i != -1:
                sensor_is_touching = False
                sensor_shape = sensor[1]
                vertex = self.get_vertices()
                sensor_origin = (vertex[1] + vertex[0]) / 2
                for segments in self.environment:
                    sensor_contact = sensor_shape.segment_query(
                        segments.a, segments.b)
                    if sensor_contact.shape is not None:
                        # add_debug_point(self.space, sensor_contact.point)
                        self.set_sensor_distance(
                            i,
                            min((sensor_origin - sensor_contact.point).length,
                                50))
                        sensor_is_touching = True

                if sensor_is_touching is False:
                    self.set_sensor_distance(i, 50)

    def set_sensor_distance(self, index, distance):
        self.sensor_distance[index] = distance

    def set_car_collision(self):
        self.car_collided = True

    def update_driver(self, driver):
        self.driver = driver

    def drive(self):
        force, angle = self.driver(torch.Tensor(self.sensor_distance))
        self.move(force.item() * 5)
        self.rotate(angle.item() / 5)

    def reward(self):
        current_pos = Vec2d(self.car_body.position)
        initial_pos = Vec2d(self.init_position)
        return (current_pos - initial_pos).length

    def reset(self):
        self.car_body.position = self.init_position
        self.car_body.angle = 0
        vertex = self.get_vertices()
        for i in range(len(self.sensors)):
            self.sensors[i][0].position = (vertex[1] + vertex[0]) / 2
            sensor_direction = Vec2d(1, 0).rotated(
                self.car_body.angle + self.sensor_angles[i])
            self.sensors[i][1].unsafe_set_endpoints(
                (0, 0), self.sensor_distance[i] * sensor_direction)
        self.car_collided = False
        offset = Vec2d(5, 0).rotated(self.car_body.angle)
        self.nose_body.position = (vertex[1] + vertex[0]) / 2 - offset