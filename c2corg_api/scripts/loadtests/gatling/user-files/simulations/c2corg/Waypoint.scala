package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import io.gatling.jdbc.Predef._

object Waypoint {
  val feeder = csv("waypoint_urls.csv").random

  val view = feed(feeder).exec(
    http("View waypoint")
      .get("${url}")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
  )
}
