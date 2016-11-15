package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import io.gatling.jdbc.Predef._

object Waypoint {
  val view = exec(http("View waypoint")
    .get("/waypoints/37202/fr/bel-oiseau")
    .headers(C2corgConf.header_html)
    .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
  )
}
