package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._


class ConsultationTopoguideAnonyme extends Simulation {

  val httpProtocol = http
    .inferHtmlResources(C2corgConf.black_list, WhiteList())
    .acceptHeader("*/*")
    .acceptEncodingHeader("gzip, deflate")

  val scn = scenario("ConsultationTopoguideAnonyme")
    .exec(Homepage.init)
    .pause(8)
    .exec(Homepage.browse)
    .pause(6)
    .exec(Outing.view)
    .pause(14)
    .exec(Route.view)
    .pause(10)
    .exec(Waypoint.view)

  val numUsers = Integer.getInteger("users", 100)
  val rampSec = Integer.getInteger("ramp", 300)

  setUp(scn.inject(rampUsers(numUsers) over (rampSec seconds))).protocols(httpProtocol)

}
