package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Waypoint {
  val feeder = csv("waypoints.csv").random

  val view = feed(feeder).exec(
    http("View waypoint")
      .get("/waypoints/${id}/${lang}/foo")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
  )
}
